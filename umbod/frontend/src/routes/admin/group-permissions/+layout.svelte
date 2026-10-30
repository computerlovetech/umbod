<script lang="ts">
  import type { Snippet } from 'svelte';
  import { onDestroy } from 'svelte';
  import { afterNavigate } from '$app/navigation';
  import { page } from '$app/state';
  import { adminApi } from '$lib/admin/infrastructure/admin-api';
  import AdminShell from '$lib/components/admin/AdminShell.svelte';
  import GroupPermissionsPage from '$lib/components/admin/group-permissions/GroupPermissionsPage.svelte';
  import GroupPermissionsWorkspace from '$lib/components/admin/group-permissions/GroupPermissionsWorkspace.svelte';
  import { BrowserGroupPermissionsLoader } from '$lib/components/admin/group-permissions/group-permissions-loader';
  import { BrowserGroupPermissionsSaver } from '$lib/components/admin/group-permissions/group-permissions-saver';
  import { GroupPermissionsRouteState } from '$lib/components/admin/group-permissions/group-permissions-route-state.svelte';
  import { GroupPermissionsWorkspaceState } from '$lib/components/admin/group-permissions/group-permissions-workspace-state.svelte';
  import { setGroupPermissionsWorkspace } from '$lib/components/admin/group-permissions/group-permissions-context';
  import type { LayoutData } from './$types';

  let { data, children }: { data: LayoutData; children: Snippet } = $props();
  const route = new GroupPermissionsRouteState(() => page.url);
  const api = adminApi();
  const state = new GroupPermissionsWorkspaceState(() => data.permissionGroups, api.groups, api.filesystem, new BrowserGroupPermissionsLoader(), new BrowserGroupPermissionsSaver(), () => route.initialTarget);
  setGroupPermissionsWorkspace(state);
  afterNavigate(() => state.activate(route.activeTab));
  onDestroy(state.dispose);
</script>

<AdminShell activeItem="groupPermissions" accountIdentity={data.accountIdentity ?? { kind: 'hidden' }} contentWidth="wide" navigationScope="/admin/group-permissions">
  <div class="admin-page">
    <GroupPermissionsPage activeTab={route.activeTab} description={route.description} backHref={route.backHref}>
      <GroupPermissionsWorkspace {state} activeTab={route.activeTab}>
        {@render children()}
      </GroupPermissionsWorkspace>
    </GroupPermissionsPage>
  </div>
</AdminShell>
