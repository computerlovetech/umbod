<script lang="ts">
  import type { Snippet } from 'svelte';
  import { onDestroy, untrack } from 'svelte';
  import { adminApi } from '#lib/admin/infrastructure/admin-api.js';
  import { afterNavigate, replaceState } from '$app/navigation';
  import { page } from '$app/state';
  import AdminShell from '#lib/components/admin/AdminShell.svelte';
  import GroupPermissionsPage from '#lib/components/admin/group-permissions/GroupPermissionsPage.svelte';
  import GroupPermissionsWorkspace from '#lib/components/admin/group-permissions/GroupPermissionsWorkspace.svelte';
  import { BrowserGroupPermissionsLoader } from '#lib/components/admin/group-permissions/group-permissions-loader.js';
  import { BrowserGroupPermissionsSaver } from '#lib/components/admin/group-permissions/group-permissions-saver.js';
  import { GroupPermissionsRouteState } from '#lib/components/admin/group-permissions/group-permissions-route-state.svelte.js';
  import { GroupPermissionsWorkspaceState } from '#lib/components/admin/group-permissions/group-permissions-workspace-state.svelte.js';
  import { setGroupPermissionsWorkspace } from '#lib/components/admin/group-permissions/group-permissions-context.js';
  import type { LayoutData } from './$types';

  let { data, children }: { data: LayoutData; children: Snippet } = $props();
  const route = new GroupPermissionsRouteState(() => new URL(page.url.href));
  function updateGroupLink(id: string): void {
    if (!page.url.searchParams.has('group')) return;
    const url = new URL(page.url.href);
    url.searchParams.set('group', id);
    replaceState(url, page.state);
  }

  const state = new GroupPermissionsWorkspaceState(() => data.permissionGroups, new BrowserGroupPermissionsLoader(), new BrowserGroupPermissionsSaver(), () => route.initialTarget, adminApi().namespaces, untrack(() => page.url.searchParams.get('group')), updateGroupLink);
  setGroupPermissionsWorkspace(state);
  $effect.pre(() => {
    const identity = data.accountIdentity ?? { kind: 'hidden' as const };
    untrack(() => state.namespaces.observeAccountIdentity(identity));
  });
  afterNavigate(({ shallow }) => {
    if (!shallow) state.activate(route.activeTab);
  });
  onDestroy(state.dispose);
</script>

<AdminShell activeItem="groupPermissions" accountIdentity={data.accountIdentity ?? { kind: 'hidden' }} contentWidth="wide" navigationScope="/admin/group-permissions">
  <div class="admin-page">
    <GroupPermissionsPage activeTab={route.activeTab} description={route.description} backHref={route.backHref}>
      <GroupPermissionsWorkspace {state}>
        {@render children()}
      </GroupPermissionsWorkspace>
    </GroupPermissionsPage>
  </div>
</AdminShell>
