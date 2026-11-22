<script lang="ts">
  import AddNamespaceButton from './AddNamespaceButton.svelte';
  import GroupPermissionsPage from '../group-permissions/GroupPermissionsPage.svelte';
  import GroupPermissionsWorkspace from '../group-permissions/GroupPermissionsWorkspace.svelte';
  import type { GroupPermissionsWorkspaceState } from '../group-permissions/group-permissions-workspace-state.svelte';
  import NamespaceManagement from './NamespaceManagement.svelte';
  import NamespacePermissions from './NamespacePermissions.svelte';
  import type { NamespaceManagementState } from './namespace-management-state.svelte';

  let { workspace, state }: { workspace?: GroupPermissionsWorkspaceState; state: NamespaceManagementState } = $props();
</script>

<GroupPermissionsPage activeTab="filesystem" description="">
  {#snippet actions()}<AddNamespaceButton {state} />{/snippet}
  {#if workspace}
    <GroupPermissionsWorkspace state={workspace}>
      <NamespacePermissions {state} />
    </GroupPermissionsWorkspace>
  {:else}
    <NamespaceManagement {state} />
    <NamespacePermissions {state} />
  {/if}
</GroupPermissionsPage>
