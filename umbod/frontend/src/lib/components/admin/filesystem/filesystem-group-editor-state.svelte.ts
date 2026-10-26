import { groupGrantSchema, type ObservedGroupPolicy, type Permission } from '$lib/admin/filesystem/domain/schemas';
import type { FilesystemAccessState, FilesystemGroup } from './filesystem-access-state.svelte';

export class FilesystemGroupEditorState {
  selectedId = $state<string | null>(null);
  editingId = $state<number | null>(null);
  draft = $state<ObservedGroupPolicy | null>(null);
  constructor(private readonly access: () => FilesystemAccessState) {}
  get selected(): FilesystemGroup | null {
    return this.access().groupEntries.find((group) => group.id === this.selectedId) ?? this.access().groupEntries[0] ?? null;
  }
  get canRepairGroupId(): boolean {
    return this.editingId !== null && !this.selected?.group_id.trim();
  }
  get validationMessage(): string {
    if (!this.draft) return '';
    if (!groupGrantSchema.safeParse(this.draft).success) return 'Enter an issuer and group ID; select at least one permission.';
    const groups = [...this.access().rows.filter((row) => row.id !== this.editingId), ...(this.access().saved?.unmanaged_groups ?? [])];
    if (groups.some((group) => group.issuer === this.draft?.issuer && group.group_id === this.draft?.group_id)) return 'This issuer and group ID already have a grant.';
    return '';
  }
  select = (id: string): void => { this.selectedId = id; };
  openAdd = (): void => {
    const group = this.selected;
    if (!group || !group.group_id.trim() || !this.access().editable) return;
    this.editingId = null;
    this.draft = { issuer: this.access().saved?.suggested_issuer ?? '', group_id: group.group_id, permissions: [] };
  };
  openEdit = (id: number): void => {
    const row = this.selected?.grants.find((grant) => grant.id === id);
    if (!row || !this.access().editable) return;
    this.editingId = row.id;
    this.draft = { issuer: row.issuer, group_id: row.group_id, permissions: [...row.permissions] };
  };
  edit = (field: 'issuer' | 'group_id', value: string): void => {
    if (this.draft && (field !== 'group_id' || this.canRepairGroupId)) this.draft = { ...this.draft, [field]: value };
  };
  toggle = (permission: Permission, checked: boolean): void => {
    if (!this.draft) return;
    this.draft = { ...this.draft, permissions: checked ? [...this.draft.permissions.filter((value) => value !== permission), permission] : this.draft.permissions.filter((value) => value !== permission) };
  };
  cancel = (): void => { this.draft = null; this.editingId = null; };
  apply = (): void => {
    if (!this.draft || this.validationMessage) return;
    const groupId = this.draft.group_id;
    const id = this.access().applyGroup(this.editingId, this.draft);
    if (id === null) return;
    this.selectedId = groupId;
    this.cancel();
  };
}
