<script lang="ts">
  import { logoutNavigation, type LogoutNavigation } from '#lib/admin/infrastructure/logout.js';
  import type { Snippet } from 'svelte';
  import type { HeaderAccountIdentityState } from '#lib/header/accountIdentity.js';
  import WorkspaceShell from '#lib/components/shared/workspace/WorkspaceShell.svelte';
  import { administrationNavigation, administrationPresentation, workspaceAccountLinks } from '#lib/workspace/navigation.js';
  import { useWorkspaceNavigationHistory } from '#lib/workspace/navigation-history-context.js';

  type AdminShellActiveItem =
    | 'insights'
    | 'agentDiagnostics'
    | 'connectors'
    | 'groups'
    | 'namespaces'
    | 'agentTokens'
    | 'groupPermissions'
    | 'systemSettings';

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
  accountLinks={workspaceAccountLinks}
  {contentWidth}
  {contentLoading}
  {navigationScope}
  {logout}
>
  {@render children()}
</WorkspaceShell>
