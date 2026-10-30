import type { GroupCatalogue } from '$lib/admin/groups/port';
import type { CatalogueGroup } from '$lib/admin/groups/domain/schemas';
import type { FilesystemAdministration } from '$lib/admin/filesystem/port';
import { canonicalGroups, replaceRootAccessSchema, type GroupGrant, type RootAccess } from '$lib/admin/filesystem/domain/schemas';
import { policyErrorMessage } from '$lib/admin/filesystem/errors';

export type FilesystemGroup = { label: string; description: string; id: string; group_id: string; registered: boolean; permissions: GroupGrant['permissions'] };

export class FilesystemAccessState {
  saved = $state.raw<RootAccess | null>(null);
  rows = $state<GroupGrant[]>([]);
  private loadedCatalogue = $state.raw<CatalogueGroup[]>([]);
  loading = $state(false);
  saving = $state(false);
  error = $state('');
  success = $state('');
  blocked = $state(false);
  confirmation = $state<'empty' | 'reload' | null>(null);
  private disposed = false;
  constructor(private readonly api: FilesystemAdministration, readonly groupCatalogue: GroupCatalogue, private readonly sharedCatalogue?: () => CatalogueGroup[]) {}
  get catalogue(): CatalogueGroup[] { return this.sharedCatalogue ? this.sharedCatalogue() : this.loadedCatalogue; }
  ensureLoaded = async (): Promise<void> => { if (!this.disposed && !this.saved && !this.loading) await this.load(); };
  get groupEntries(): FilesystemGroup[] {
    const ids = [...new Set([...this.catalogue.map((group) => group.group_id), ...this.rows.map((row) => row.group_id), ...(this.saved?.groups.map((group) => group.group_id) ?? []), ...(this.saved?.blocked_group_ids ?? [])])];
    return ids.map((group_id) => ({ label: this.catalogue.find((group) => group.group_id === group_id)?.label ?? 'Unregistered group', description: this.catalogue.find((group) => group.group_id === group_id)?.description ?? '', id: group_id, group_id, registered: this.catalogue.some((group) => group.group_id === group_id), permissions: this.rows.find((row) => row.group_id === group_id)?.permissions ?? [] }));
  }
  get busy(): boolean { return this.loading || this.saving; }
  get editable(): boolean { return !!this.saved && this.saved.status !== 'conflict' && !this.busy && !this.blocked; }
  get groups(): GroupGrant[] { return this.rows.map(({ group_id, permissions }) => ({ group_id, permissions: [...permissions] })); }
  get dirty(): boolean { return !!this.saved && canonicalGroups(this.groups) !== canonicalGroups(this.saved.groups); }
  get validationMessage(): string {
    if (!replaceRootAccessSchema.safeParse({ expected_revision: this.saved?.revision ?? '', groups: this.groups }).success) return 'Enter a group ID; select at least one permission. Remove duplicate groups.';
    if (this.groups.some((group) => this.saved?.blocked_group_ids.includes(group.group_id))) return 'This group is managed outside this editor.';
    return '';
  }
  get canSave(): boolean { return this.editable && !this.validationMessage && (this.dirty || this.saved?.status === 'uninitialized'); }
  private accept(policy: RootAccess): void {
    this.saved = policy;
    this.rows = policy.groups.map((group) => ({ ...group, permissions: [...group.permissions] }));
    this.blocked = false;
  }
  load = async (): Promise<void> => {
    if (this.disposed || this.busy) return;
    this.loading = true;
    this.error = '';
    this.success = '';
    try {
      const [policy, catalogue] = await Promise.all([this.api.getRootAccess(), this.sharedCatalogue ? Promise.resolve(this.sharedCatalogue()) : this.groupCatalogue.list()]);
      if (!this.disposed) { this.loadedCatalogue = catalogue; this.accept(policy); }
    }
    catch (error) { if (!this.disposed) this.error = policyErrorMessage(error); }
    finally { if (!this.disposed) this.loading = false; }
  };
  dispose = (): void => { this.disposed = true; };
  setGroupPermissions = (groupId: string, permissions: GroupGrant['permissions']): void => {
    if (!this.editable || this.saved?.blocked_group_ids.includes(groupId)) return;
    this.rows = this.rows.filter((row) => row.group_id !== groupId);
    if (permissions.length) this.rows = [...this.rows, { group_id: groupId, permissions: [...permissions] }];
    this.success = '';
  };
  requestReload = (): void => { if (!this.busy) { if (this.dirty) this.confirmation = 'reload'; else void this.load(); } };
  cancelConfirmation = (): void => { this.confirmation = null; };
  confirm = async (): Promise<void> => {
    const action = this.confirmation;
    this.confirmation = null;
    if (action === 'reload') await this.load();
    if (action === 'empty') await this.persist();
  };
  save = async (): Promise<void> => {
    if (!this.canSave) return;
    if (this.rows.length === 0) { this.confirmation = 'empty'; return; }
    await this.persist();
  };
  private async persist(): Promise<void> {
    if (!this.canSave || !this.saved) return;
    this.saving = true;
    this.error = '';
    this.success = '';
    try {
      const policy = await this.api.replaceRootAccess({ expected_revision: this.saved.revision, groups: this.groups });
      if (!this.disposed) { this.accept(policy); this.success = 'Filesystem access saved.'; }
    } catch (error) {
      if (!this.disposed) {
        this.error = policyErrorMessage(error);
        this.blocked = true;
      }
    } finally { if (!this.disposed) this.saving = false; }
  }
}
