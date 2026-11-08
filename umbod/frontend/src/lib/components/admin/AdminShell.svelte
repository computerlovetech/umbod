<script lang="ts">
  import { logoutNavigation, type LogoutNavigation } from '$lib/admin/infrastructure/logout';
  import type { Snippet } from 'svelte';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
  import WorkspaceShell from '$lib/components/shared/workspace/WorkspaceShell.svelte';
  import { administrationNavigation, administrationPresentation } from '$lib/workspace/navigation';
  import { useWorkspaceNavigationHistory } from '$lib/workspace/navigation-history-context';

  type AdminShellActiveItem =
    | 'analytics'
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

  const navigationHistory = useWorkspaceNavigationHistory();
</script>

<WorkspaceShell
  {...administrationPresentation}
  navigationItems={administrationNavigation}
  backLink={{ label: 'Back to workspace', href: navigationHistory?.returnHref ?? '/dashboard' }}
  {activeItem}
  {accountIdentity}
  {contentWidth}
  {contentLoading}
  {navigationScope}
  {logout}
>
  {@render children()}
</WorkspaceShell>
