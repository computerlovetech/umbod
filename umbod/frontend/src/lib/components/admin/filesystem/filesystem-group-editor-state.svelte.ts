import { groupGrantSchema, type ObservedGroupPolicy, type Permission } from '$lib/admin/filesystem/domain/schemas';
import type { FilesystemAccessState, GroupDraft } from './filesystem-access-state.svelte';

export class FilesystemGroupEditorState {
  selectedId = $state<number | null>(null);
  editingId = $state<number | null>(null);
  draft = $state<ObservedGroupPolicy | null>(null);
  constructor(private readonly access: () => FilesystemAccessState) {}
  get selected(): GroupDraft | null {
    return this.access().rows.find((row) => row.id === this.selectedId) ?? this.access().rows[0] ?? null;
  }
  get validationMessage(): string {
    if (!this.draft) return '';
    if (!groupGrantSchema.safeParse(this.draft).success) return 'Enter an issuer and group ID; select at least one permission.';
    const groups = [...this.access().rows.filter((row) => row.id !== this.editingId), ...(this.access().saved?.unmanaged_groups ?? [])];
    if (groups.some((group) => group.issuer === this.draft?.issuer && group.group_id === this.draft?.group_id)) return 'This issuer and group ID already have a grant.';
    return '';
  }
  select = (id: number): void => { this.selectedId = id; };
  openAdd = (): void => {
    if (!this.access().editable) return;
    this.editingId = null;
    this.draft = { issuer: this.access().saved?.suggested_issuer ?? '', group_id: '', permissions: [] };
  };
  openEdit = (): void => {
    const row = this.selected;
    if (!row || !this.access().editable) return;
    this.editingId = row.id;
    this.draft = { issuer: row.issuer, group_id: row.group_id, permissions: [...row.permissions] };
  };
  edit = (field: 'issuer' | 'group_id', value: string): void => {
    if (this.draft) this.draft = { ...this.draft, [field]: value };
  };
  toggle = (permission: Permission, checked: boolean): void => {
    if (!this.draft) return;
    this.draft = { ...this.draft, permissions: checked ? [...this.draft.permissions.filter((value) => value !== permission), permission] : this.draft.permissions.filter((value) => value !== permission) };
  };
  cancel = (): void => { this.draft = null; this.editingId = null; };
  apply = (): void => {
    if (!this.draft || this.validationMessage) return;
    const id = this.access().applyGroup(this.editingId, this.draft);
    if (id === null) return;
    this.selectedId = id;
    this.cancel();
  };
}
