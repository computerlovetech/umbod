<script lang="ts">
  import GroupPermissionsManager from '$lib/components/admin/group-permissions/GroupPermissionsManager.svelte';
  import DelayedSpinner from '$lib/components/admin/shared/DelayedSpinner.svelte';
  import { getGroupPermissionsWorkspace } from '$lib/components/admin/group-permissions/group-permissions-context';

  const workspace = getGroupPermissionsWorkspace();
</script>

<svelte:head><title>Connectors · Group permissions</title></svelte:head>

{#if workspace.selectedGroup && !workspace.selectedGroup.registered}
  <p>This group is not registered for connector permissions. Manage its filesystem access or register it on the Groups page.</p>
{:else if workspace.connectors}
  <GroupPermissionsManager state={workspace.connectors} />
{:else}
  <DelayedSpinner active label="Loading group permissions" />
{/if}
