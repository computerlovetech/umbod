import type { GroupCatalogue } from '$lib/admin/groups/port';
import { createGroupSchema, updateGroupSchema, type CatalogueGroup } from '$lib/admin/groups/domain/schemas';
import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';

import type { IdentityGroupDirectory } from '$lib/identity-directory/port';
import { GroupSuggestions } from './group-suggestions.svelte';

export class GroupsState {
  readonly suggestions: GroupSuggestions;
  private entries = $state.raw<CatalogueGroup[]>([]);
  private editing = $state.raw<CatalogueGroup | null>(null);
  private disposed = false;
  private generation = 0;
  private _query = $state('');
  private _groupId = $state('');
  private _label = $state('');
  private _description = $state('');
  private _formOpen = $state(false);
  private _pending = $state(false);
  private _error = $state('');
  private _message = $state('');
  private _conflict = $state(false);
  private _missing = $state(false);
  private _denied = $state(false);
  private _deleting = $state<string | null>(null);

  constructor(private readonly catalogue: GroupCatalogue, groups: CatalogueGroup[], directory: IdentityGroupDirectory) {
    this.suggestions = new GroupSuggestions(directory);
    this.entries = groups.map((group) => ({ ...group }));
  }
  get query(): string { return this._query; }
  get groupId(): string { return this._groupId; }
  get label(): string { return this._label; }
  get description(): string { return this._description; }
  get formOpen(): boolean { return this._formOpen; }
  get pending(): boolean { return this._pending; }
  get error(): string { return this._error; }
  get message(): string { return this._message; }
  get conflict(): boolean { return this._conflict; }
  get missing(): boolean { return this._missing; }
  get denied(): boolean { return this._denied; }
  get deleting(): string | null { return this._deleting; }
  get groups(): readonly CatalogueGroup[] { return this._denied ? [] : this.entries.map((group) => ({ ...group })); }
  get filteredGroups(): readonly CatalogueGroup[] {
    const query = this._query.toLocaleLowerCase();
    return this.groups.filter((group) => [group.group_id, group.label, group.description].some((value) => value.toLocaleLowerCase().includes(query)));
  }
  get isEditing(): boolean { return this.editing !== null; }
  get canSave(): boolean { return !this.disposed && !this._pending && !this._denied && !this._conflict && !this._missing; }
  setQuery = (value: string): void => { this._query = value; };
  setGroupId = (value: string): void => {
    if (this.editing || this._pending) return;
    this._groupId = value;
    this.suggestions.search(value);
  };
  setLabel = (value: string): void => { if (!this._pending) this._label = value; };
  setDescription = (value: string): void => { if (!this._pending) this._description = value; };
  create = (): void => { if (this.disposed || this._pending || this._denied) return; this.open(null); };
  edit = (group: CatalogueGroup): void => { if (this._pending || this._denied) return; this.open(group); };
  private open(group: CatalogueGroup | null): void {
    ++this.generation;
    this.suggestions.close();
    if (!group) this.suggestions.open();
    this.editing = group ? { ...group } : null;
    this._groupId = group?.group_id ?? '';
    this._label = group?.label ?? '';
    this._description = group?.description ?? '';
    this._formOpen = true;
    this._error = '';
    this._message = '';
    this._conflict = false;
    this._missing = false;
    this._deleting = null;
  }
  cancel = (): void => {
    if (this._pending) return;
    ++this.generation;
    this._formOpen = false;
    this.suggestions.close();
    this._deleting = null;
    this._error = '';
    this._conflict = false;
  };
  requestDelete = (groupId: string): void => {
    if (this._pending || this._denied) return;
    this.cancel();
    this._deleting = groupId;
  };
  save = async (): Promise<void> => {
    if (!this.canSave || !this._formOpen) return;
    const body = { group_id: this._groupId, label: this._label, description: this._description };
    const parsed = this.editing ? updateGroupSchema.safeParse({ ...body, expected_revision: this.editing.revision }) : createGroupSchema.safeParse(body);
    if (!parsed.success) { this._error = parsed.error.issues.map((issue) => issue.message).join('. '); return; }
    if (!this.editing && this.entries.some((group) => group.group_id === body.group_id)) { this._error = 'A group with this exact provider group ID already exists.'; return; }
    const generation = ++this.generation;
    this._pending = true;
    this._error = '';
    try {
      if ('expected_revision' in parsed.data) {
        const updated = await this.catalogue.update(updateGroupSchema.parse(parsed.data));
        if (!this.active(generation)) return;
        if (updated.group_id !== body.group_id) throw new Error('Group identity changed in response');
        this.entries = this.entries.map((group) => group.group_id === updated.group_id ? updated : group);
        this.editing = updated;
        this._label = updated.label;
        this._description = updated.description;
      } else {
        await this.catalogue.create(parsed.data);
        const groups = await this.catalogue.list();
        if (!this.active(generation)) return;
        this.entries = groups;
        const registered = groups.find((group) => group.group_id === parsed.data.group_id);
        if (!registered) throw new Error('Created group missing from catalogue');
        if (registered.label !== parsed.data.label || registered.description !== parsed.data.description) {
          this._error = 'This provider group ID now exists with different metadata. Your draft is preserved; review the existing group before editing it.';
          return;
        }
      }
      this._formOpen = false;
      this.suggestions.close();
      this._message = 'Group saved. Permissions are unchanged.';
    } catch (error) { if (this.active(generation)) this.fail(error, 'save'); }
    finally { if (this.active(generation)) this._pending = false; }
  };
  reloadRevision = async (): Promise<void> => {
    if (this.disposed || this._pending || !this.editing || this._denied) return;
    const generation = ++this.generation;
    this._pending = true;
    try {
      const groups = await this.catalogue.list();
      if (!this.active(generation)) return;
      this.entries = groups;
      const latest = groups.find((group) => group.group_id === this._groupId);
      this._missing = !latest;
      if (latest) this.editing = latest;
      this._conflict = false;
      this._error = latest ? '' : 'This group no longer exists. Your draft is preserved.';
      this._message = latest ? 'Latest revision loaded. Review your preserved draft and save to retry.' : '';
    } catch (error) { if (this.active(generation)) this.fail(error, 'reload'); }
    finally { if (this.active(generation)) this._pending = false; }
  };
  delete = async (): Promise<void> => {
    if (this.disposed || this._pending || this._denied || this._deleting === null) return;
    const id = this._deleting;
    const generation = ++this.generation;
    this._pending = true;
    this._error = '';
    try {
      await this.catalogue.delete(id);
      if (!this.active(generation)) return;
      this.entries = this.entries.filter((group) => group.group_id !== id);
      this._deleting = null;
      this._message = 'Group deleted.';
    } catch (error) { if (this.active(generation)) this.fail(error, 'delete'); }
    finally { if (this.active(generation)) this._pending = false; }
  };
  private active(generation: number): boolean { return !this.disposed && generation === this.generation; }
  private fail(error: unknown, operation: 'save' | 'delete' | 'reload'): void {
    if (error instanceof AuthenticationRequiredError || (error instanceof HttpError && [401, 403].includes(error.status))) {
      this._denied = true;
      this.suggestions.close();
      this._formOpen = false;
      this._deleting = null;
      this._error = 'Administration access is no longer available. Sign in with an authorized account.';
    } else if (error instanceof HttpError && error.status === 409) {
      this._conflict = operation === 'save' && this.isEditing;
      this._error = operation === 'delete' ? 'This group is in use. Remove its connector, capability and filesystem references before deleting.' : this.isEditing ? 'This group changed elsewhere. Your draft is preserved. Reload the latest revision before retrying.' : 'A group with this exact provider group ID already exists.';
    } else if (error instanceof HttpError && error.status === 404) {
      this._missing = true;
      this._error = 'This group no longer exists. Your draft is preserved.';
    } else this._error = 'The operation could not be completed. Your draft is preserved; try again.';
  }
  dispose = (): void => { this.disposed = true; ++this.generation; this.suggestions.close(); };
}
