<script lang="ts">
  import type { Snippet } from 'svelte';
  import { onDestroy, untrack } from 'svelte';
  import { adminApi } from '#lib/admin/infrastructure/admin-api.js';
  import { afterNavigate } from '$app/navigation';
  import { page } from '$app/state';
  import AdminShell from '#lib/components/admin/AdminShell.svelte';
  import AddNamespaceButton from '#lib/components/admin/filesystem/AddNamespaceButton.svelte';
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
  const state = new GroupPermissionsWorkspaceState(() => data.permissionGroups, new BrowserGroupPermissionsLoader(), new BrowserGroupPermissionsSaver(), () => route.initialTarget, adminApi().namespaces);
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
      {#snippet actions()}
        {#if route.activeTab === 'filesystem'}<AddNamespaceButton state={state.namespaces} />{/if}
      {/snippet}
      <GroupPermissionsWorkspace {state}>
        {@render children()}
      </GroupPermissionsWorkspace>
    </GroupPermissionsPage>
  </div>
</AdminShell>
