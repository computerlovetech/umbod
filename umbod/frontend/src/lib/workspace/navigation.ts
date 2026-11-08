export interface WorkspaceNavigationItem {
  id: string;
  label: string;
  href: string;
}

export const workspacePresentation = {
  workspaceLabel: 'Workspace',
  homeHref: '/dashboard',
  accountFallback: 'Your account',
  sidebarLabel: 'Workspace sidebar',
  navigationLabel: 'Workspace navigation'
};

const dashboardNavigation: readonly WorkspaceNavigationItem[] = [
  { id: 'dashboard', label: 'Dashboard', href: '/dashboard' },
  { id: 'files', label: 'Files', href: '/files' },
  { id: 'gettingStarted', label: 'Getting started', href: '/getting-started' }
];

const administratorNavigation: readonly WorkspaceNavigationItem[] = [
  ...dashboardNavigation,
  { id: 'analytics', label: 'Log analytics', href: '/admin/analytics' },
  { id: 'connectors', label: 'Connectors', href: '/admin/connectors' },
  { id: 'groups', label: 'Groups', href: '/admin/groups' },
  { id: 'groupPermissions', label: 'Group permissions', href: '/admin/group-permissions/connectors' },
  { id: 'instanceConfiguration', label: 'Instance settings', href: '/admin/instance-configuration' }
];

export function usesWorkspaceShell(pathname: string): boolean {
  return ['/admin', '/dashboard', '/files', '/getting-started'].some((root: string): boolean => pathname === root || pathname.startsWith(`${root}/`));
}

export function workspaceNavigation(adminAllowed: boolean): readonly WorkspaceNavigationItem[] {
  return adminAllowed ? administratorNavigation : dashboardNavigation;
}
