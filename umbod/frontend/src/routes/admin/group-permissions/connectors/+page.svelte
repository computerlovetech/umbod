<script lang="ts">
  import GroupPermissionsManager from '#lib/components/admin/group-permissions/GroupPermissionsManager.svelte';
  import DelayedSpinner from '#lib/components/admin/shared/DelayedSpinner.svelte';
  import { getGroupPermissionsWorkspace } from '#lib/components/admin/group-permissions/group-permissions-context.js';

  const workspace = getGroupPermissionsWorkspace();
</script>

<svelte:head><title>Connectors · Permissions</title></svelte:head>

{#if workspace.connectors}
  <GroupPermissionsManager state={workspace.connectors} />
{:else}
  <DelayedSpinner active label="Loading group permissions" />
{/if}
