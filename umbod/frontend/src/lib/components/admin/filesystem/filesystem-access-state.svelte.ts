import type { FilesystemAdministration } from '$lib/admin/filesystem/port';
import { canonicalGroups, replaceRootAccessSchema, type ObservedGroupPolicy, type Permission, type RootAccess } from '$lib/admin/filesystem/domain/schemas';
import { policyErrorMessage } from '$lib/admin/filesystem/errors';

export type GroupDraft = ObservedGroupPolicy & { id: number };

export class FilesystemAccessState {
  saved = $state.raw<RootAccess | null>(null);
  rows = $state<GroupDraft[]>([]);
  loading = $state(false);
  saving = $state(false);
  error = $state('');
  success = $state('');
  blocked = $state(false);
  confirmation = $state<'empty' | 'reload' | null>(null);
  private nextId = 0;
  private disposed = false;
  constructor(private readonly api: FilesystemAdministration) {}
  get busy(): boolean { return this.loading || this.saving; }
  get editable(): boolean { return !!this.saved && this.saved.status !== 'conflict' && !this.busy && !this.blocked; }
  get groups(): ObservedGroupPolicy[] { return this.rows.map(({ issuer, group_id, permissions }) => ({ issuer, group_id, permissions: [...permissions] })); }
  get dirty(): boolean { return !!this.saved && canonicalGroups(this.groups) !== canonicalGroups(this.saved.groups); }
  get validationMessage(): string {
    if (!replaceRootAccessSchema.safeParse({ expected_revision: this.saved?.revision ?? '', groups: this.groups }).success) return 'Enter an issuer and group ID; select at least one permission. Remove duplicate groups.';
    if (this.groups.some((group) => this.saved?.unmanaged_groups.some((unmanaged) => group.issuer === unmanaged.issuer && group.group_id === unmanaged.group_id))) return 'This group already has a recursive grant.';
    return '';
  }
  get canSave(): boolean { return this.editable && !this.validationMessage && (this.dirty || this.saved?.status === 'uninitialized'); }
  private accept(policy: RootAccess): void {
    this.saved = policy;
    this.rows = policy.groups.map((group) => ({ ...group, permissions: [...group.permissions], id: this.nextId++ }));
    this.blocked = false;
  }
  load = async (): Promise<void> => {
    if (this.busy) return;
    this.loading = true;
    this.error = '';
    this.success = '';
    try { const policy = await this.api.getRootAccess(); if (!this.disposed) this.accept(policy); }
    catch (error) { if (!this.disposed) this.error = policyErrorMessage(error); }
    finally { if (!this.disposed) this.loading = false; }
  };
  dispose = (): void => { this.disposed = true; };
  add = (): void => {
    if (!this.editable) return;
    this.rows = [...this.rows, { id: this.nextId++, issuer: this.saved?.suggested_issuer || '', group_id: '', permissions: [] }];
    this.success = '';
  };
  edit = (id: number, field: 'issuer' | 'group_id', value: string): void => {
    if (!this.editable) return;
    this.rows = this.rows.map((row) => row.id === id ? { ...row, [field]: value } : row);
    this.success = '';
  };
  toggle = (id: number, permission: Permission, checked: boolean): void => {
    if (!this.editable) return;
    this.rows = this.rows.map((row) => row.id === id ? { ...row, permissions: checked ? [...row.permissions.filter((value) => value !== permission), permission] : row.permissions.filter((value) => value !== permission) } : row);
    this.success = '';
  };
  remove = (id: number): void => { if (this.editable) { this.rows = this.rows.filter((row) => row.id !== id); this.success = ''; } };
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
