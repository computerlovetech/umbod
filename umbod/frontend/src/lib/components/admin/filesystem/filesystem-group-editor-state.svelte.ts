import type { Permission } from '$lib/admin/filesystem/domain/schemas';
import type { FilesystemAccessState, FilesystemGroup } from './filesystem-access-state.svelte';

export class FilesystemGroupEditorState {
  selectedId = $state<string | null>(null);
  constructor(private readonly access: () => FilesystemAccessState, private readonly selection?: () => string | null) {}
  get selected(): FilesystemGroup | null {
    if (this.selection) return this.access().groupEntries.find((group) => group.id === this.selection!()) ?? null;
    return this.access().groupEntries.find((group) => group.id === this.selectedId) ?? this.access().groupEntries[0] ?? null;
  }
  get permissions(): Permission[] { return this.selected?.permissions ?? []; }
  get assignmentMessage(): string {
    if (this.selected && this.access().saved?.blocked_group_ids.includes(this.selected.group_id)) return 'Permissions for this group are managed outside this editor. Ask an operator to resolve its access rules before assigning permissions here.';
    return '';
  }
  get editable(): boolean { return this.access().editable && !!this.selected && !this.assignmentMessage; }
  select = (id: string): void => { this.selectedId = id; };
  toggle = (permission: Permission, checked: boolean): void => {
    if (!this.editable || !this.selected) return;
    const permissions = checked ? [...this.permissions.filter((value) => value !== permission), permission] : this.permissions.filter((value) => value !== permission);
    this.access().setGroupPermissions(this.selected.group_id, permissions);
  };
}
