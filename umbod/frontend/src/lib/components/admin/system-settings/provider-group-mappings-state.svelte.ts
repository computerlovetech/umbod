import type { GroupCatalogue } from '#lib/admin/groups/port.js';
import { AuthenticationRequiredError, HttpError } from '#lib/admin/infrastructure/transport.js';
import {
  providerGroupMappingListSchema,
  type ProviderGroupMapping,
  type ProviderGroupMappings,
  type ProviderGroupMappingsPatch
} from '#lib/admin/system-settings/domain/provider-group-mappings.js';
import type { ProviderGroupMappingsAdministration } from '#lib/admin/system-settings/provider-group-mappings-port.js';

type Row = Readonly<{ id: number; mapping: Readonly<ProviderGroupMapping> }>;
type SavedMappings = { source: ProviderGroupMappings['source']; rows: readonly Row[] };
type GroupOption = { value: string; label: string; disabled?: boolean };
type Catalogue = { kind: 'loading' | 'failed' } | { kind: 'ready'; options: GroupOption[]; ids: ReadonlySet<string> };
type Draft = { operation: 'set'; rows: readonly Row[] } | { operation: 'reset' };
type Failure = { kind: 'read' | 'write' | 'access'; message: string };

export class ProviderGroupMappingsState {
  #saved = $state.raw<SavedMappings>();
  #draft = $state.raw<Draft>();
  #catalogue = $state.raw<Catalogue>({ kind: 'loading' });
  #failure = $state.raw<Failure>();
  #pending = $state.raw<AbortController>();
  #catalogueRequest: AbortController | undefined;
  #nextRowId = 0;

  constructor(
    private readonly settings: ProviderGroupMappingsAdministration,
    private readonly groups: Pick<GroupCatalogue, 'list'>
  ) {}

  get ready(): boolean { return this.#saved !== undefined; }
  get busy(): boolean { return this.ready && this.#pending !== undefined; }
  get loading(): boolean { return !this.ready && !this.#failure; }
  get dirty(): boolean { return this.#draft !== undefined; }
  get #resetting(): boolean { return this.#draft?.operation === 'reset'; }
  get canReset(): boolean {
    return this.#saved?.source === 'admin_override' && !this.#resetting;
  }
  get failure(): string | undefined { return this.#failure?.message; }
  get canRetry(): boolean { return this.#failure?.kind === 'read'; }
  get catalogueStatus(): Catalogue['kind'] { return this.#catalogue.kind; }
  get editable(): boolean { return this.ready && !this.busy && !this.#resetting && this.#catalogue.kind === 'ready'; }
  get rows(): readonly Row[] {
    if (this.#resetting) return [];
    return this.#draft?.operation === 'set' ? this.#draft.rows : this.#saved?.rows ?? [];
  }

  #validation = $derived.by((): { message?: string; patch?: ProviderGroupMappingsPatch } => {
    if (!this.dirty) return {};
    if (this.#resetting) return { patch: { operation: 'reset' } };
    if (this.#catalogue.kind !== 'ready') return {};
    const mappings = this.rows.map(({ mapping }): Readonly<ProviderGroupMapping> => mapping);
    const result = providerGroupMappingListSchema.safeParse(mappings);
    if (!result.success) {
      const listIssue = result.error.issues.find(({ path }): boolean => path.length === 1);
      return { message: listIssue?.message ?? 'Complete every field before saving.' };
    }
    const { ids } = this.#catalogue;
    if (result.data.some(({ group_id }): boolean => !ids.has(group_id))) {
      return { message: 'Replace or remove unavailable groups before saving.' };
    }
    return { patch: { operation: 'set', mappings: result.data } };
  });

  get validationMessage(): string | undefined { return this.#validation.message; }
  get canSave(): boolean { return !this.busy && this.#validation.patch !== undefined; }

  start = (): void => {
    void this.load();
    void this.loadGroups();
  };

  load = async (): Promise<void> => {
    if (this.#pending || this.dirty || this.#failure?.kind === 'access') return;
    await this.#request((signal): Promise<ProviderGroupMappings> => this.settings.get(signal), 'read');
  };

  loadGroups = async (): Promise<void> => {
    if (this.#catalogueRequest || this.#failure?.kind === 'access') return;
    const request = new AbortController();
    this.#catalogueRequest = request;
    this.#catalogue = { kind: 'loading' };
    try {
      const groups = await this.groups.list();
      if (request.signal.aborted) return;
      this.#catalogue = {
        kind: 'ready',
        options: groups.map(({ group_id, label }): GroupOption => ({ value: group_id, label: `${label} (${group_id})` })),
        ids: new Set(groups.map(({ group_id }): string => group_id))
      };
    } catch (error) {
      if (!request.signal.aborted && !this.#revokeAccess(error)) this.#catalogue = { kind: 'failed' };
    } finally {
      if (!request.signal.aborted) this.#catalogueRequest = undefined;
    }
  };

  groupOptions(groupId: string): GroupOption[] {
    const label = groupId || 'Select a group';
    if (this.#catalogue.kind !== 'ready') return [{ value: groupId, label, disabled: true }];
    if (this.#catalogue.ids.has(groupId)) return [...this.#catalogue.options];
    return [{ value: groupId, label: groupId ? `${groupId} (unavailable)` : label, disabled: true }, ...this.#catalogue.options];
  }

  add = (): void => {
    if (!this.editable) return;
    this.#replace([...this.rows, this.#row({ external_value: '', group_id: '' })]);
  };

  change(id: number, field: keyof ProviderGroupMapping, value: string): void {
    if (!this.editable) return;
    this.#replace(this.rows.map((row): Row => row.id === id ? { ...row, mapping: { ...row.mapping, [field]: value } } : row));
  }

  remove(id: number): void {
    if (!this.editable) return;
    this.#replace(this.rows.filter((row): boolean => row.id !== id));
  }

  reset = (): void => {
    if (!this.canReset || this.busy) return;
    this.#draft = { operation: 'reset' };
    this.#failure = undefined;
  };

  discard = (): void => {
    if (this.busy) return;
    this.#draft = undefined;
    this.#failure = undefined;
  };

  save = async (): Promise<void> => {
    const patch = this.#validation.patch;
    if (this.busy || !patch) return;
    await this.#request((signal): Promise<ProviderGroupMappings> => this.settings.update(patch, signal), 'write');
  };

  dispose = (): void => {
    this.#pending?.abort();
    this.#catalogueRequest?.abort();
    this.#pending = undefined;
    this.#catalogueRequest = undefined;
  };

  #replace(rows: readonly Row[]): void {
    this.#draft = { operation: 'set', rows };
    this.#failure = undefined;
  }

  #row(mapping: ProviderGroupMapping): Row {
    return { id: this.#nextRowId++, mapping };
  }

  async #request(send: (signal: AbortSignal) => Promise<ProviderGroupMappings>, operation: 'read' | 'write'): Promise<void> {
    const request = new AbortController();
    this.#pending = request;
    this.#failure = undefined;
    try {
      const { source, mappings } = await send(request.signal);
      if (request.signal.aborted) return;
      this.#saved = { source, rows: mappings.map((mapping): Row => this.#row(mapping)) };
      this.#draft = undefined;
    } catch (error) {
      if (!request.signal.aborted && !this.#revokeAccess(error)) this.#recordFailure(error, operation);
    } finally {
      if (!request.signal.aborted) this.#pending = undefined;
    }
  }

  #recordFailure(error: unknown, operation: 'read' | 'write'): void {
    if (operation === 'read') {
      this.#failure = { kind: 'read', message: 'Could not load provider group mappings.' };
      return;
    }
    this.#failure = {
      kind: 'write',
      message: error instanceof HttpError && error.status === 422
        ? 'The mappings were not saved. Check that each target group is registered.'
        : 'Could not confirm that your changes were saved. Try again.'
    };
    if (error instanceof HttpError && error.status === 422) void this.loadGroups();
  }

  #revokeAccess(error: unknown): boolean {
    const signInNeeded = error instanceof AuthenticationRequiredError;
    if (!signInNeeded && !(error instanceof HttpError && error.status === 403)) return false;
    this.dispose();
    this.#saved = undefined;
    this.#draft = undefined;
    this.#catalogue = { kind: 'loading' };
    this.#failure = {
      kind: 'access',
      message: signInNeeded ? 'Sign in again to access system settings.' : 'You do not have permission to access system settings.'
    };
    return true;
  }
}
