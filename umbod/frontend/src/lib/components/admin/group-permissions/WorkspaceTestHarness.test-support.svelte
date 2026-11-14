<script lang="ts">
  import NamespaceManagement from '../filesystem/NamespaceManagement.svelte';
  import AdminShell from '../AdminShell.svelte';
  import GroupPermissionsPage from './GroupPermissionsPage.svelte';
  import GroupPermissionsWorkspace from './GroupPermissionsWorkspace.svelte';
  import GroupPermissionsManager from './GroupPermissionsManager.svelte';
  import type { GroupPermissionsTab } from './group-permissions-route-state.svelte';
  import type { GroupPermissionsWorkspaceState } from './group-permissions-workspace-state.svelte';

  let { state, tab }: { state: GroupPermissionsWorkspaceState; tab: GroupPermissionsTab } = $props();
</script>

<AdminShell activeItem="groupPermissions" accountIdentity={{ kind: 'hidden' }} navigationScope="/admin/group-permissions">
  <GroupPermissionsPage activeTab={tab} description="Assign group permissions.">
    <GroupPermissionsWorkspace {state}>
      {#if tab === 'connectors'}
        {#if state.connectors}<GroupPermissionsManager state={state.connectors} />{/if}
      {:else}
        <NamespaceManagement state={state.namespaces} />
      {/if}
    </GroupPermissionsWorkspace>
  </GroupPermissionsPage>
</AdminShell>
