import { tick } from 'svelte';
import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';
import type { NodeSharingApi } from '../api';
import type { NodeSummary } from '../domain/schemas';
import { nodeAccessSchema, replaceAccessSchema, eligibleSharingGroupsSchema, sharingPermissions, type NodeAccess, type SharingGroup, type SharingPermission } from '../domain/sharing';

type DraftGroup = { readonly group_id: string; readonly label: string; readonly description: string; readonly permissions: readonly SharingPermission[] };

export class SharingDialogState {
  private target = $state.raw<NodeSummary>();
  private stage = $state<'closed' | 'loading' | 'ready' | 'error' | 'denied' | 'sign-in'>('closed');
  private saving = $state(false);
  private draft = $state.raw<readonly DraftGroup[]>([]);
  private catalogue = $state.raw<readonly SharingGroup[]>([]);
  private blocked: string[] = [];
  private revision = '';
  private banner = $state('');
  private recovery = $state(false);
  private invalidRecipients = $state(false);
  private catalogueLoading = $state(false);
  private catalogueFailure = $state('');
  private query = $state('');
  private announcement = $state('');
  private generation = 0;
  private catalogueGeneration = 0;
  private controller: AbortController | undefined;
  private trigger: HTMLElement | undefined;
  private location = '';
  private disposed = false;

  constructor(private readonly api: NodeSharingApi, private readonly revoke: (id: string) => void, private readonly recheck: (id: string) => void) {}

  get node(): NodeSummary | undefined { return this.target; }
  get open(): boolean { return this.stage !== 'closed'; }
  get phase(): string { return this.stage; }
  get pending(): boolean { return this.saving; }
  get groups(): readonly DraftGroup[] { return this.draft; }
  get permissions(): typeof sharingPermissions { return sharingPermissions; }
  get error(): string { return this.banner; }
  get needsReload(): boolean { return this.recovery; }
  get needsGroupsRefresh(): boolean { return this.invalidRecipients; }
  get groupsLoading(): boolean { return this.catalogueLoading; }
  get groupsError(): string { return this.catalogueFailure; }
  get filter(): string { return this.query; }
  get status(): string { return this.announcement; }
  get editable(): boolean { return this.stage === 'ready' && !this.saving && !this.recovery; }
  get canSave(): boolean { return this.editable && !this.invalidRecipients && !this.catalogueLoading && !this.catalogueFailure && replaceAccessSchema.safeParse({ groups: this.draft.map(({ group_id, permissions }) => ({ group_id, permissions })) }).success; }
  get availableGroups(): readonly SharingGroup[] {
    const query = this.query.toLocaleLowerCase();
    return this.catalogue.filter((group) => !this.blocked.includes(group.group_id) && !this.draft.some((entry) => entry.group_id === group.group_id) && [group.label, group.description, group.group_id].some((text) => text.toLocaleLowerCase().includes(query)));
  }

  get groupOptions(): { value: string; label: string }[] {
    return this.availableGroups.map((group) => ({
      value: group.group_id,
      label: group.label
    }));
  }

  show = async (node: NodeSummary, trigger?: HTMLElement): Promise<void> => {
    if (this.disposed || this.open || this.saving) return;
    this.target = Object.freeze(structuredClone(node));
    this.trigger = trigger;
    this.location = typeof window === 'undefined' ? '' : window.location.href;
    this.query = '';
    this.draft = [];
    this.catalogue = [];
    await this.reloadLatest();
  };

  reloadLatest = async (): Promise<void> => {
    if (!this.target || this.saving || this.disposed) return;
    const generation = ++this.generation;
    ++this.catalogueGeneration;
    this.catalogueLoading = false;
    this.controller?.abort();
    this.controller = new AbortController();
    this.stage = 'loading';
    this.banner = '';
    const id = this.target.id;
    try {
      const [access, groups] = await Promise.all([
        this.api.inspectAccess(id, this.controller.signal), this.api.listEligibleSharingGroups(id, this.controller.signal)
      ]);
      if (!this.current(generation)) return;
      const view = nodeAccessSchema.parse(access);
      if (view.node_id !== id) throw new Error('Unexpected node access');
      this.catalogue = Object.freeze(eligibleSharingGroupsSchema.parse({ groups }).groups.map((group) => Object.freeze(group)));
      this.accept(view);
      this.recovery = false;
      this.invalidRecipients = false;
      this.catalogueFailure = '';
      this.stage = 'ready';
    } catch (error) {
      if (!this.current(generation)) return;
      this.failRead(error, id);
    }
  };

  refreshGroups = async (): Promise<void> => {
    if (!this.editable || !this.target || this.catalogueLoading) return;
    const generation = this.generation;
    const catalogueGeneration = ++this.catalogueGeneration;
    const id = this.target.id;
    this.catalogueLoading = true;
    this.catalogueFailure = '';
    try {
      const groups = await this.api.listEligibleSharingGroups(id, this.controller?.signal);
      if (!this.current(generation) || catalogueGeneration !== this.catalogueGeneration) return;
      this.catalogue = Object.freeze(eligibleSharingGroupsSchema.parse({ groups }).groups.map((group) => Object.freeze(group)));
      this.invalidRecipients = this.draft.some((entry) => !groups.some((group) => group.group_id === entry.group_id));
      this.banner = this.invalidRecipients ? 'Remove unavailable groups before saving. Your changes have been kept.' : '';
    } catch (error) {
      if (!this.current(generation) || catalogueGeneration !== this.catalogueGeneration) return;
      if (error instanceof AuthenticationRequiredError || error instanceof HttpError && [401, 403, 404].includes(error.status)) this.failRead(error, id);
      else this.catalogueFailure = "Couldn't refresh registered groups. Try again.";
    } finally {
      if (this.current(generation) && catalogueGeneration === this.catalogueGeneration) this.catalogueLoading = false;
    }
  };

  changeFilter = (value: string): void => { if (this.editable) this.query = value; };

  add = (id: string): void => {
    if (!this.editable) return;
    const group = this.availableGroups.find((entry) => entry.group_id === id);
    if (!group) return;
    this.draft = Object.freeze([...this.draft, Object.freeze({ ...group, permissions: Object.freeze(['discover', 'read'] as SharingPermission[]) })]);
    this.query = '';
  };

  remove = (id: string): void => {
    if (!this.editable) return;
    this.draft = Object.freeze(this.draft.filter((group) => group.group_id !== id));
    if (this.invalidRecipients && !this.catalogueLoading) this.invalidRecipients = this.draft.some((entry) => !this.catalogue.some((group) => group.group_id === entry.group_id));
  };

  changePermission = (id: string, permission: SharingPermission, enabled: boolean): void => {
    if (!this.editable) return;
    this.draft = Object.freeze(this.draft.map((group) => group.group_id === id ? Object.freeze({ ...group, permissions: Object.freeze(enabled ? [...new Set([...group.permissions, permission])] : group.permissions.filter((value) => value !== permission)) }) : group));
  };

  save = async (): Promise<void> => {
    if (!this.canSave || !this.target) return;
    const id = this.target.id;
    const generation = this.generation;
    const body = replaceAccessSchema.parse({ groups: this.draft.map(({ group_id, permissions }) => ({ group_id, permissions })) });
    this.saving = true;
    this.banner = '';
    try {
      const view = nodeAccessSchema.parse(await this.api.replaceAccess(id, this.revision, body));
      if (!this.current(generation)) return;
      if (view.node_id !== id) throw new Error('Unexpected node access');
      this.accept(view);
      this.announcement = `Sharing updated for “${this.target.name || 'Files'}”.`;
      this.revoke(id);
      this.recheck(id);
      this.saving = false;
      await this.close();
    } catch (error) {
      if (!this.current(generation)) return;
      if (error instanceof AuthenticationRequiredError || error instanceof HttpError && [401, 403, 404].includes(error.status)) this.failRead(error, id);
      else if (error instanceof HttpError && error.status === 412) {
        this.recovery = true;
        this.banner = 'Access changed elsewhere. Your changes have been kept. Reload latest to discard this draft and review current access.';
      } else if (error instanceof HttpError && error.status === 422) {
        this.invalidRecipients = true;
        this.banner = 'A group may no longer be available. Your changes have been kept. Refresh registered groups and review recipients.';
      } else {
        this.recovery = true;
        this.banner = "Couldn't confirm the change. Do not submit again until you reload latest access. Reloading discards this draft so you can review the authoritative result.";
      }
    } finally {
      if (this.current(generation)) this.saving = false;
    }
  };

  close = async (): Promise<void> => {
    if (this.saving || !this.open) return;
    const trigger = this.trigger;
    const location = this.location;
    this.reset();
    const generation = this.generation;
    await tick();
    if (!this.disposed && generation === this.generation && typeof window !== 'undefined' && window.location.href === location) {
      (trigger?.isConnected ? trigger : document.getElementById('files-heading'))?.focus();
    }
  };

  reset = (): void => {
    ++this.generation;
    ++this.catalogueGeneration;
    this.controller?.abort();
    this.stage = 'closed';
    this.saving = false;
    this.catalogueLoading = false;
    this.target = undefined;
    this.trigger = undefined;
    this.draft = [];
    this.recovery = false;
    this.invalidRecipients = false;
    this.catalogueFailure = '';
    this.banner = '';
    this.query = '';
    this.catalogue = [];
    this.blocked = [];
    this.revision = '';
  };

  dispose = (): void => { this.disposed = true; this.reset(); };

  private current(generation: number): boolean { return !this.disposed && generation === this.generation && (typeof window === 'undefined' || window.location.href === this.location); }

  private accept(view: NodeAccess): void {
    this.revision = view.revision;
    this.blocked = view.blocked_group_ids;
    this.draft = Object.freeze(view.groups.map((entry) => {
      const metadata = this.catalogue.find((group) => group.group_id === entry.group_id);
      return Object.freeze({ ...entry, label: metadata?.label || entry.group_id, description: metadata?.description || '', permissions: Object.freeze([...entry.permissions]) });
    }));
  }

  private failRead(error: unknown, id: string): void {
    if (error instanceof AuthenticationRequiredError || error instanceof HttpError && error.status === 401) {
      this.stage = 'sign-in'; this.banner = 'Sign in to manage sharing.'; this.revoke(id);
    } else if (error instanceof HttpError && [403, 404].includes(error.status)) {
      this.stage = 'denied'; this.banner = 'You can no longer manage sharing for this item.'; this.revoke(id);
    } else { this.stage = 'error'; this.banner = "Couldn't load sharing. Try loading latest access again."; }
  }
}
