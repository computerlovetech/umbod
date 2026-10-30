<script lang="ts">
  import { logoutNavigation, type LogoutNavigation } from '$lib/admin/infrastructure/logout';
  import type { Snippet } from 'svelte';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
  import WorkspaceShell from '$lib/components/shared/workspace/WorkspaceShell.svelte';
  import { workspaceNavigation, workspacePresentation } from '$lib/workspace/navigation';

  type AdminShellActiveItem =
    | 'overview'
    | 'connectors'
    | 'groups'
    | 'groupPermissions'
    | 'instanceConfiguration';

  type AdminShellProps = {
    activeItem: AdminShellActiveItem;
    accountIdentity: HeaderAccountIdentityState;
    contentWidth?: 'default' | 'wide';
    contentLoading?: boolean;
    navigationScope?: string;
    children: Snippet;
    logout?: LogoutNavigation;
  };

  let { activeItem, accountIdentity, contentWidth = 'default', contentLoading = false, navigationScope, children, logout = logoutNavigation }: AdminShellProps = $props();

  const navigationItems = workspaceNavigation(true);
</script>

<WorkspaceShell
  {...workspacePresentation}
  {navigationItems}
  {activeItem}
  {accountIdentity}
  {contentWidth}
  {contentLoading}
  {navigationScope}
  {logout}
>
  {@render children()}
</WorkspaceShell>
