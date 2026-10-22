<script lang="ts">
  import { logoutNavigation, type LogoutNavigation } from '$lib/admin/infrastructure/logout';
  import type { Snippet } from 'svelte';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
  import WorkspaceShell from '$lib/components/shared/workspace/WorkspaceShell.svelte';
  import type { WorkspaceNavigationItem } from '$lib/components/shared/workspace/workspace-shell-state.svelte';

  type AdminShellActiveItem =
    | 'overview'
    | 'connectors'
    | 'groupPermissions'
    | 'mcpSetup'
    | 'instanceConfiguration';

  type AdminShellProps = {
    activeItem: AdminShellActiveItem;
    accountIdentity: HeaderAccountIdentityState;
    contentWidth?: 'default' | 'wide';
    children: Snippet;
    logout?: LogoutNavigation;
  };

  let { activeItem, accountIdentity, contentWidth = 'default', children, logout = logoutNavigation }: AdminShellProps = $props();

  const navigationItems: readonly WorkspaceNavigationItem[] = [
    { id: 'overview', label: 'Overview', href: '/admin' },
    { id: 'connectors', label: 'Connectors', href: '/admin/connectors' },
    { id: 'groupPermissions', label: 'Group permissions', href: '/admin/group-permissions' },
    { id: 'mcpSetup', label: 'MCP setup guide', href: '/admin/mcp-setup' },
    {
      id: 'instanceConfiguration',
      label: 'Instance settings',
      href: '/admin/instance-configuration'
    }
  ];
</script>

<WorkspaceShell
  workspaceLabel="Administration"
  homeHref="/admin"
  {navigationItems}
  {activeItem}
  {accountIdentity}
  accountFallback="Admin area"
  sidebarLabel="Admin sidebar"
  navigationLabel="Admin navigation"
  {contentWidth}
  {logout}
>
  {@render children()}
</WorkspaceShell>
