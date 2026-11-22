import { HttpError } from '#lib/admin/infrastructure/transport.js';
import type { NamespaceAdministration } from '#lib/admin/filesystem/namespaces-port.js';
import { createNamespaceSchema, namespaceErrorSchema, type DeleteNamespace, type SharedNamespace, type NamespaceGroup } from '#lib/admin/filesystem/domain/namespaces.js';

type AccessDraft = Readonly<{ access: 'none' | NamespaceGroup['access']; revision: number }>;

type DeleteSnapshot = Readonly<{ id: string; name: string; revisions: Readonly<DeleteNamespace> }>;

const deletionErrors: Readonly<Partial<Record<string, string>>> = {
  filesystem_namespace_not_empty: 'Could not delete namespace because it still contains files or folders.',
  filesystem_namespace_active_uploads: 'Could not delete namespace because it has active uploads. Wait for the uploads to finish or expire.',
  filesystem_namespace_not_found: 'This namespace is no longer available. Reload namespaces to update the list.',
  filesystem_policy_unavailable: 'This namespace cannot be managed right now.',
  filesystem_policy_invalid: 'Could not delete namespace with these revisions. Reload namespaces before trying again.'
};

export class NamespaceManagementState {
  private entries = $state.raw<SharedNamespace[]>([]);
  private accessDrafts = $state.raw<Record<string, Record<string, AccessDraft>>>({});
  private permissionsPending = $state(false);
  private permissionMessage = $state('');
  private reloadRequested = $state(false);
  private activated = $state(false);
  private editorVisible = $state(false);
  private deletion = $state.raw<DeleteSnapshot | null>(null);
  private selectedId = $state<string | null>(null);
  private draftName = $state('');
  private draftDescription = $state('');
  private rootRevision = $state<number | null>(null);
  private revision = $state<number | null>(null);
  private pending = $state(false);
  private loading = $state(false);
  private message = $state('');
  private conflicted = $state(false);
  private accessStale = $state(false);
  private inventoryUnavailable = $state(false);
  private identityFingerprint: string | undefined;
  private generation = 0;
  private disposed = false;

  constructor(private readonly api: NamespaceAdministration, private readonly readSelectedGroupId: () => string | null) {}

  readonly accessOptions = [{ value: 'none', label: 'No access' }, { value: 'read', label: 'Read' }, { value: 'read_write', label: 'Read and write' }];
  get selectedGroupId(): string | null { return this.readSelectedGroupId(); }
  get namespaces(): readonly SharedNamespace[] { return structuredClone(this.entries); }
  get editorOpen(): boolean { return this.editorVisible; }
  get selected(): string | null { return this.deletion?.id ?? this.selectedId; }
  get deleteName(): string | undefined { return this.deletion?.name; }
  get confirmingDelete(): boolean { return this.deletion !== null; }
  get canOpenEditor(): boolean { return !this.busy && !this.confirmingDelete && !this.disposed; }
  get canDelete(): boolean {
    return this.canOpenEditor && !this.editorOpen && !this.hasUnsavedChanges && !this.needsReload && !this.reloadConfirmation;
  }
  get name(): string { return this.draftName; }
  get description(): string { return this.draftDescription; }
  get busy(): boolean { return this.pending || this.permissionsPending || this.loading; }
  get error(): string { return this.message; }
  get conflict(): boolean { return this.conflicted; }
  get inventoryLoaded(): boolean { return this.activated && !this.inventoryUnavailable; }
  get needsReload(): boolean { return this.accessStale || this.inventoryUnavailable; }
  get canSave(): boolean { return this.editorOpen && !this.disposed && !this.busy && !this.conflicted && createNamespaceSchema.safeParse({ name: this.draftName, groups: [] }).success; }
  get canAssignAccess(): boolean { return this.selectedGroupId !== null && this.canOpenEditor && !this.editorOpen && !this.needsReload; }
  get writing(): boolean { return this.pending || this.permissionsPending; }
  get savingPermissions(): boolean { return this.permissionsPending; }
  get permissionError(): string { return this.permissionMessage; }
  get hasUnsavedChanges(): boolean { return Object.values(this.accessDrafts).some((draft) => Object.keys(draft).length > 0); }
  get selectedGroupDirty(): boolean { return this.selectedGroupId !== null && Object.keys(this.accessDrafts[this.selectedGroupId] ?? {}).length > 0; }
  get canSavePermissions(): boolean { return this.canAssignAccess && this.selectedGroupDirty && !this.conflicted; }
  get reloadConfirmation(): boolean { return this.reloadRequested; }
  get permissionFeedback(): { message: string; tone: 'saving' | 'error' | 'warning' | 'muted'; icon: string } {
    if (this.permissionsPending) return { message: 'Saving changes…', tone: 'saving', icon: '' };
    if (this.permissionMessage) return { message: this.permissionMessage, tone: 'error', icon: '!' };
    if (this.selectedGroupDirty) return { message: 'Unsaved changes', tone: 'warning', icon: '•' };
    return { message: 'All changes saved', tone: 'muted', icon: '✓' };
  }
  private authoritativeAccess(namespaceId: string, groupId: string | null): 'none' | NamespaceGroup['access'] {
    return this.entries.find((entry) => entry.id === namespaceId)?.groups.find((group) => group.group_id === groupId)?.access ?? 'none';
  }
  access = (namespaceId: string): 'none' | NamespaceGroup['access'] => {
    const groupId = this.selectedGroupId;
    return (groupId === null ? undefined : this.accessDrafts[groupId]?.[namespaceId]?.access) ?? this.authoritativeAccess(namespaceId, groupId);
  };

  discardSelectedDraft = (): void => {
    if (this.busy || this.disposed || this.selectedGroupId === null) return;
    const drafts = { ...this.accessDrafts };
    delete drafts[this.selectedGroupId];
    this.accessDrafts = drafts;
    this.permissionMessage = '';
  };

  ensureLoaded = (): Promise<void> => this.activated ? Promise.resolve() : this.load();

  requestReload = (): void => {
    if (!this.canOpenEditor || this.editorOpen) return;
    if (this.hasUnsavedChanges) this.reloadRequested = true;
    else void this.load();
  };

  resolveReload = (decision: 'discard' | 'cancel'): void => {
    if (!this.reloadRequested || this.busy || this.disposed) return;
    this.reloadRequested = false;
    if (decision === 'discard') void this.load();
  };

  observeAccountIdentity = (identity: import('#lib/header/accountIdentity.js').HeaderAccountIdentityState): void => {
    const fingerprint = JSON.stringify(identity.kind === 'visible' ? ['visible', identity.hiddenValues.id] : ['hidden']);
    if (this.disposed || fingerprint === this.identityFingerprint) return;
    const previous = this.identityFingerprint;
    this.identityFingerprint = fingerprint;
    if (previous !== undefined) {
      if (this.activated) void this.load();
      else { ++this.generation; this.accessDrafts = {}; }
    }
  };

  load = async (notice = ''): Promise<void> => {
    if (this.disposed) return;
    this.activated = true;
    this.pending = false;
    this.permissionsPending = false;
    this.accessDrafts = {};
    this.permissionMessage = '';
    this.reloadRequested = false;
    const generation = ++this.generation;
    this.loading = true;
    this.inventoryUnavailable = true;
    this.entries = [];
    this.message = notice;
    this.deletion = null;
    this.clearDraft();
    try {
      const entries = await this.api.list();
      if (this.disposed || generation !== this.generation) return;
      this.entries = entries;
      this.inventoryUnavailable = false;
      this.accessStale = false;
    } catch {
      if (!this.disposed && generation === this.generation) {
        this.message = notice ? notice + ' Could not reload shared namespaces.' : 'Could not load shared namespaces.';
      }
    } finally {
      if (!this.disposed && generation === this.generation) this.loading = false;
    }
  };

  private clearDraft(): void {
    this.editorVisible = false;
    this.selectedId = null;
    this.draftName = '';
    this.draftDescription = '';
    this.rootRevision = null;
    this.revision = null;
    this.conflicted = false;
  }

  beginCreate = (): void => {
    if (!this.canOpenEditor) return;
    ++this.generation;
    this.clearDraft();
    this.message = '';
    this.editorVisible = true;
  };

  beginEdit = (id: string): void => {
    if (!this.canOpenEditor) return;
    const entry = this.entries.find((item) => item.id === id);
    if (!entry) return;
    ++this.generation;
    this.clearDraft();
    this.message = '';
    this.editorVisible = true;
    this.selectedId = entry.id;
    this.draftName = entry.name;
    this.draftDescription = entry.description;
    this.rootRevision = entry.root_revision;
    this.revision = entry.revision;
  };

  beginDelete = (id: string): void => {
    if (!this.canDelete) return;
    const entry = this.entries.find((item) => item.id === id);
    if (!entry) return;
    this.message = '';
    this.deletion = {
      id: entry.id, name: entry.name,
      revisions: { expected_revision: entry.revision, expected_root_revision: entry.root_revision }
    };
  };

  cancelDelete = (): void => {
    if (!this.busy && !this.disposed) this.deletion = null;
  };

  confirmDelete = async (): Promise<void> => {
    const snapshot = this.deletion;
    if (!snapshot || this.busy || this.disposed || this.hasUnsavedChanges || this.needsReload) return;
    const generation = ++this.generation;
    this.pending = true;
    try {
      await this.api.delete(snapshot.id, snapshot.revisions);
      if (this.disposed || generation !== this.generation) return;
      this.entries = this.entries.filter((entry) => entry.id !== snapshot.id);
    } catch (error) {
      if (this.disposed || generation !== this.generation) return;
      const envelope = namespaceErrorSchema.safeParse(error instanceof HttpError ? error.body : undefined);
      const code = envelope.success ? envelope.data.detail.code : undefined;
      if (code === 'filesystem_policy_stale') {
        await this.load('Namespace changed. Review the refreshed list before confirming deletion again.');
        return;
      }
      this.message = (code && Object.hasOwn(deletionErrors, code) ? deletionErrors[code] : undefined)
        ?? 'Could not delete shared namespace. Reload namespaces to check whether it was deleted.';
    } finally {
      if (!this.disposed && generation === this.generation) {
        this.pending = false;
        this.deletion = null;
      }
    }
  };

  closeEditor = (): void => {
    if (this.busy || this.disposed || !this.editorOpen) return;
    ++this.generation;
    this.clearDraft();
    this.message = '';
  };

  changeName = (name: string): void => { if (this.editorOpen && !this.disposed && !this.busy) this.draftName = name; };

  changeDescription = (description: string): void => { if (this.editorOpen && !this.disposed && !this.busy) this.draftDescription = description; };

  refreshConflict = async (): Promise<void> => {
    if (!this.editorOpen || this.disposed || !this.conflicted || this.busy || !this.selectedId) return;
    const generation = ++this.generation;
    const id = this.selectedId;
    this.loading = true;
    try {
      const entries = await this.api.list();
      if (this.disposed || generation !== this.generation) return;
      this.entries = entries;
      this.inventoryUnavailable = false;
      const entry = entries.find((item) => item.id === id);
      if (!entry) { this.clearDraft(); this.message = 'Namespace unavailable.'; return; }
      this.revision = entry.revision;
      this.rootRevision = entry.root_revision;
      this.conflicted = false;
      this.message = '';
    } catch {
      if (!this.disposed && generation === this.generation) this.message = 'Could not refresh shared namespaces.';
    } finally {
      if (!this.disposed && generation === this.generation) this.loading = false;
    }
  };

  save = async (): Promise<void> => {
    if (!this.canSave) return;
    const generation = this.generation;
    const id = this.selectedId;
    const entry = this.entries.find((item) => item.id === id);
    const input = createNamespaceSchema.parse({ name: this.draftName, groups: entry?.groups ?? [], ...(this.draftDescription ? { description: this.draftDescription } : {}) });
    this.pending = true;
    this.message = '';
    try {
      const result = id && this.revision !== null && this.rootRevision !== null
        ? await this.api.update(id, { ...input, description: this.draftDescription, expected_revision: this.revision, expected_root_revision: this.rootRevision })
        : await this.api.create(input);
      if (this.disposed || generation !== this.generation) return;
      this.reconcile(result);
      if (id !== null && this.revision !== null) this.acknowledgeMetadataRevision(id, this.revision, result.revision);
      this.clearDraft();
    } catch (error) {
      if (this.disposed || generation !== this.generation) return;
      this.conflicted = error instanceof HttpError && error.status === 409 && id !== null;
      this.message = this.conflicted
        ? 'Namespace changed. Refresh before reapplying your changes.'
        : error instanceof HttpError && error.status === 409
          ? 'A shared namespace with this name already exists.'
          : 'Could not save shared namespace.';
    } finally {
      if (!this.disposed && generation === this.generation) this.pending = false;
    }
  };

  stageAccess = (namespaceId: string, access: string): void => {
    if (!this.canAssignAccess || !['none', 'read', 'read_write'].includes(access)) return;
    const groupId = this.selectedGroupId;
    const entry = this.entries.find((item) => item.id === namespaceId);
    if (groupId === null || !entry) return;
    const draft = { ...this.accessDrafts[groupId] };
    if (this.authoritativeAccess(namespaceId, groupId) === access) delete draft[namespaceId];
    else draft[namespaceId] = { access: access as AccessDraft['access'], revision: draft[namespaceId]?.revision ?? entry.revision };
    this.accessDrafts = { ...this.accessDrafts, [groupId]: draft };
    this.permissionMessage = '';
  };

  savePermissions = async (): Promise<void> => {
    if (!this.canSavePermissions) return;
    const groupId = this.selectedGroupId;
    if (groupId === null) return;
    const snapshot = Object.entries(this.accessDrafts[groupId] ?? {});
    const generation = this.generation;
    this.permissionsPending = true;
    this.permissionMessage = '';
    let acknowledged = 0;
    try {
      for (const [namespaceId, draftSnapshot] of snapshot) {
        if (this.disposed || generation !== this.generation || this.selectedGroupId !== groupId) return;
        const entry = this.entries.find((item) => item.id === namespaceId);
        if (!entry) throw new Error('Namespace unavailable');
        const groups = entry.groups.filter((group) => group.group_id !== groupId);
        if (draftSnapshot.access !== 'none') groups.push({ group_id: groupId, access: draftSnapshot.access });
        const result = await this.api.update(namespaceId, { name: entry.name, groups, expected_revision: draftSnapshot.revision });
        if (this.disposed || generation !== this.generation) return;
        this.reconcile(result);
        const draft = { ...this.accessDrafts[groupId] };
        delete draft[namespaceId];
        this.accessDrafts = { ...this.accessDrafts, [groupId]: draft };
        ++acknowledged;
      }
    } catch (error) {
      if (this.disposed || generation !== this.generation) return;
      this.accessStale = error instanceof HttpError && error.status === 409;
      const failure = this.accessStale
        ? 'Namespace access changed. Reload and review before trying again.'
        : 'Could not save namespace access. Unsaved changes remain.';
      this.permissionMessage = acknowledged > 0 ? `${acknowledged} namespace permission changes saved. ${failure}` : failure;
    } finally {
      if (!this.disposed && generation === this.generation) this.permissionsPending = false;
    }
  };

  private acknowledgeMetadataRevision(namespaceId: string, expectedRevision: number, revision: number): void {
    this.accessDrafts = Object.fromEntries(Object.entries(this.accessDrafts).map(([groupId, drafts]) => {
      const draft = drafts[namespaceId];
      return [groupId, draft?.revision === expectedRevision ? { ...drafts, [namespaceId]: { ...draft, revision } } : drafts];
    }));
  }

  private reconcile(entry: SharedNamespace): void {
    this.entries = [...this.entries.filter((item) => item.id !== entry.id), entry].sort((left, right) => left.name.localeCompare(right.name));
  }

  dispose = (): void => {
    this.disposed = true;
    this.accessDrafts = {};
    this.permissionsPending = false;
    this.permissionMessage = '';
    this.reloadRequested = false;
    this.accessStale = false;
    this.inventoryUnavailable = false;
    ++this.generation;
    this.entries = [];
    this.pending = false;
    this.loading = false;
    this.message = '';
    this.deletion = null;
    this.clearDraft();
  };
}
