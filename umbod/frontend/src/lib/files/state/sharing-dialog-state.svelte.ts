import { tick } from 'svelte';
import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';
import type { NodeSharingApi } from '../api';
import type { NodeSummary } from '../domain/schemas';
import { nodeAccessSchema, replaceAccessSchema, sharingPermissions, type NodeAccess, type ReplaceAccess, type SharingRecipient, type SharingRecipientType, type SharingPermission } from '../domain/sharing';
import { RecipientSearchState } from './recipient-search-state.svelte';

type DraftRecipient = { readonly recipient: Readonly<SharingRecipient>; readonly id: string; readonly label: string; readonly permissions: readonly SharingPermission[] };

function recipientId(recipient: SharingRecipient): string { return recipient.type === 'group' ? recipient.group_id : recipient.user_id; }

export class SharingDialogState {
  private target = $state.raw<NodeSummary>();
  private stage = $state<'closed' | 'loading' | 'refreshing' | 'ready' | 'error' | 'denied' | 'sign-in'>('closed');
  private saving = $state(false);
  private scope = $state<SharingRecipientType>('group');
  private requestedScope = $state<SharingRecipientType>();
  private draft = $state.raw<readonly DraftRecipient[]>([]);
  private blocked: string[] = [];
  private revision = '';
  private original = '';
  private banner = $state('');
  private recovery = $state(false);
  private announcement = $state('');
  private generation = 0;
  private controller: AbortController | undefined;
  private trigger: HTMLElement | undefined;
  private location = '';
  private disposed = false;
  readonly search: RecipientSearchState;

  constructor(private readonly api: NodeSharingApi, private readonly revoke: (id: string) => void, private readonly recheck: (id: string) => void, private readonly label: (node: NodeSummary) => string = (node: NodeSummary): string => node.name || 'Files') {
    this.search = new RecipientSearchState(api, this.handleSearchAuthorityFailure);
  }

  get node(): NodeSummary | undefined { return this.target; }
  get nodeName(): string { return this.target ? this.label(this.target) : 'Files'; }
  get open(): boolean { return this.stage !== 'closed'; }
  get phase(): string { return this.stage; }
  get pending(): boolean { return this.saving; }
  get refreshing(): boolean { return this.stage === 'refreshing'; }
  get recipientType(): SharingRecipientType { return this.scope; }
  get confirmingSwitch(): boolean { return this.requestedScope !== undefined; }
  get recipients(): readonly DraftRecipient[] { return this.draft; }
  get permissions(): typeof sharingPermissions { return sharingPermissions; }
  get error(): string { return this.banner; }
  get needsReload(): boolean { return this.recovery; }
  get filter(): string { return this.search.query; }
  get status(): string { return this.announcement; }
  get editable(): boolean { return this.stage === 'ready' && !this.saving && !this.recovery && !this.confirmingSwitch && !this.search.unavailable; }
  get canSave(): boolean { return this.editable && replaceAccessSchema.safeParse(this.body()).success; }
  get dirty(): boolean { return JSON.stringify(this.body()) !== this.original; }
  get pickerLabel(): string { return this.scope === 'group' ? 'Add group' : 'Add user'; }
  get searchPlaceholder(): string { return this.scope === 'group' ? 'Search groups by name or ID' : 'Search users by name'; }
  get saveLabel(): string { return this.scope === 'group' ? 'Save group sharing' : 'Save user sharing'; }
  get availableRecipients(): readonly SharingRecipient[] {
    return this.search.recipients.filter((recipient) => recipient.type === this.scope && !this.blocked.includes(recipientId(recipient)) && !this.draft.some((entry) => entry.id === recipientId(recipient)));
  }
  get recipientOptions(): { value: string; label: string }[] {
    return this.availableRecipients.map((recipient) => ({ value: recipientId(recipient), label: recipient.label ? `${recipient.label} (${recipientId(recipient)})` : recipientId(recipient) }));
  }

  show = async (node: NodeSummary, trigger?: HTMLElement): Promise<void> => {
    if (this.disposed || this.open || this.saving) return;
    this.target = Object.freeze(structuredClone(node));
    this.trigger = trigger;
    this.location = typeof window === 'undefined' ? '' : window.location.href;
    this.scope = 'group';
    this.draft = [];
    await this.reloadLatest();
  };

  selectRecipientType = async (recipientType: SharingRecipientType): Promise<void> => {
    if (this.saving || this.stage !== 'ready' || recipientType === this.scope || this.confirmingSwitch) return;
    if (this.dirty) {
      this.requestedScope = recipientType;
      return;
    }
    await this.switchTo(recipientType);
  };

  keepEditing = (): void => { this.requestedScope = undefined; };

  discardAndSwitch = async (): Promise<void> => {
    const recipientType = this.requestedScope;
    if (!recipientType || this.saving) return;
    this.requestedScope = undefined;
    await this.switchTo(recipientType);
  };

  reloadLatest = async (): Promise<void> => { await this.loadLatest(this.scope); };

  private loadLatest = async (recipientType: SharingRecipientType): Promise<void> => {
    if (!this.target || this.saving || this.disposed) return;
    const generation = ++this.generation;
    this.controller?.abort();
    this.controller = new AbortController();
    this.search.reset();
    this.stage = this.stage === 'ready' || this.refreshing ? 'refreshing' : 'loading';
    this.banner = '';
    this.requestedScope = undefined;
    const id = this.target.id;
    try {
      const view = nodeAccessSchema.parse(await this.api.inspectAccess(id, recipientType, this.controller.signal));
      if (!this.current(generation)) return;
      if (view.node_id !== id) throw new Error('Unexpected node access');
      this.scope = recipientType;
      this.accept(view);
      this.recovery = false;
      this.search.target(id, this.scope);
      this.stage = 'ready';
    } catch (error) {
      if (this.current(generation)) this.failRead(error, id);
    }
  };

  changeFilter = (value: string): void => { if (this.editable) this.search.changeQuery(value); };

  add = (id: string): void => {
    if (!this.editable) return;
    const recipient = this.availableRecipients.find((entry) => recipientId(entry) === id);
    if (!recipient) return;
    this.draft = Object.freeze([...this.draft, Object.freeze({ recipient, id, label: recipient.label || id, permissions: Object.freeze(['discover', 'read'] as SharingPermission[]) })]);
    this.search.changeQuery('');
  };

  remove = (id: string): void => {
    if (this.editable) this.draft = Object.freeze(this.draft.filter((entry) => entry.id !== id));
  };

  changePermission = (id: string, permission: SharingPermission, enabled: boolean): void => {
    if (!this.editable) return;
    this.draft = Object.freeze(this.draft.map((entry) => entry.id === id ? Object.freeze({ ...entry, permissions: Object.freeze(enabled ? [...new Set([...entry.permissions, permission])] : entry.permissions.filter((value) => value !== permission)) }) : entry));
  };

  save = async (): Promise<void> => {
    if (!this.canSave || !this.target) return;
    const id = this.target.id;
    const generation = this.generation;
    const body = replaceAccessSchema.parse(this.body());
    this.saving = true;
    this.banner = '';
    this.search.reset();
    try {
      const view = nodeAccessSchema.parse(await this.api.replaceAccess(id, this.revision, body, this.scope));
      if (!this.current(generation)) return;
      if (view.node_id !== id) throw new Error('Unexpected node access');
      this.accept(view);
      this.announcement = `Sharing updated for “${this.nodeName}”.`;
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
        this.recovery = true;
        this.banner = 'A recipient may no longer be available. Your changes have been kept. Reload latest to discard this draft and review current access.';
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
    this.controller?.abort();
    this.search.reset();
    this.stage = 'closed';
    this.saving = false;
    this.target = undefined;
    this.trigger = undefined;
    this.draft = [];
    this.requestedScope = undefined;
    this.recovery = false;
    this.banner = '';
    this.blocked = [];
    this.revision = '';
    this.original = '';
  };

  dispose = (): void => { this.disposed = true; this.reset(); };

  private handleSearchAuthorityFailure = async (error: unknown): Promise<void> => {
    if (!this.target) return;
    const generation = this.generation;
    const id = this.target.id;
    if (error instanceof AuthenticationRequiredError || error instanceof HttpError && error.status === 401) {
      this.failRead(error, id);
      return;
    }
    try {
      const view = nodeAccessSchema.parse(await this.api.inspectAccess(id, this.scope, this.controller?.signal));
      if (this.current(generation) && view.node_id !== id) this.failRead(new Error('Unexpected node access'), id);
    } catch (inspectionError) {
      if (this.current(generation)) this.failRead(inspectionError, id);
    }
  };

  private async switchTo(recipientType: SharingRecipientType): Promise<void> {
    await this.loadLatest(recipientType);
  }

  private body(): ReplaceAccess {
    return { grants: this.draft.map(({ recipient, permissions }) => ({ recipient: recipient.type === 'group' ? { type: 'group', group_id: recipient.group_id } : { type: 'user', user_id: recipient.user_id }, permissions: [...permissions] })) };
  }

  private current(generation: number): boolean { return !this.disposed && generation === this.generation && (typeof window === 'undefined' || window.location.href === this.location); }

  private accept(view: NodeAccess): void {
    this.revision = view.revision;
    this.blocked = view.blocked_recipients.flatMap((recipient) => recipient.type === this.scope ? [recipient.type === 'group' ? recipient.group_id : recipient.user_id] : []);
    this.draft = Object.freeze(view.grants.flatMap(({ recipient, permissions }) => recipient.type !== this.scope ? [] : [Object.freeze({ recipient: Object.freeze(recipient), id: recipientId(recipient), label: recipient.label || recipientId(recipient), permissions: Object.freeze([...permissions]) })]));
    this.original = JSON.stringify(this.body());
  }

  private failRead(error: unknown, id: string): void {
    if (error instanceof AuthenticationRequiredError || error instanceof HttpError && error.status === 401) {
      this.stage = 'sign-in'; this.banner = 'Sign in to manage sharing.'; this.revoke(id);
    } else if (error instanceof HttpError && [403, 404].includes(error.status)) {
      this.stage = 'denied'; this.banner = 'You can no longer manage sharing for this item.'; this.revoke(id);
    } else { this.stage = 'error'; this.banner = "Couldn't load sharing. Try loading latest access again."; }
  }
}
