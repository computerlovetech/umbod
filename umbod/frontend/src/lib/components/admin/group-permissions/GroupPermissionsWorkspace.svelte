<script lang="ts">
  import type { Snippet } from 'svelte';
  import AdminSplitWorkspace from '../shared/AdminSplitWorkspace.svelte';
  import Button from '../shared/Button.svelte';
  import GroupPermissionsGroupList from './GroupPermissionsGroupList.svelte';
  import GroupPermissionsGroupHeader from './GroupPermissionsGroupHeader.svelte';
  import type { GroupPermissionsWorkspaceState } from './group-permissions-workspace-state.svelte';

  let { state, children }: { state: GroupPermissionsWorkspaceState; children: Snippet } = $props();
</script>

<AdminSplitWorkspace ariaLabel="Group permissions workspace" sidebarLabel="Groups" sidebarHeading="Groups" count={state.groupEntries.length} detailLabel="Permission editor">
  {#snippet sidebar()}
    <GroupPermissionsGroupList groups={state.groupEntries} groupId={(group) => group.id} selectedGroupId={state.selectedGroupId} onselect={state.requestSelection} />
  {/snippet}
  {#snippet detail()}
    {#if state.selectedGroup}
      <GroupPermissionsGroupHeader groupId={state.selectedGroup.group_id} label={state.selectedGroup.label} description={state.selectedGroup.description}>
      </GroupPermissionsGroupHeader>
    {/if}
    {#if state.pendingSelection !== null}
      <div class="selection-warning" role="alert">
        <p>You have unsaved permission changes. Discard them or cancel before switching groups.</p>
        <Button variant="danger" onclick={() => state.resolveSelection('discard')}>Discard changes</Button>
        <Button variant="secondary" onclick={() => state.resolveSelection('cancel')}>Cancel</Button>
      </div>
    {/if}
    {@render children()}
  {/snippet}
</AdminSplitWorkspace>

<style>
  .selection-warning { background: var(--admin-warning-bg); border: 1px solid var(--admin-warning-border); border-radius: var(--admin-radius); color: var(--admin-warning-text); font-size: 13px; margin-bottom: 18px; padding: 14px 16px; }
  .selection-warning p { margin: 0 0 12px; }
</style>
