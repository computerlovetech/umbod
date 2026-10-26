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
  { id: 'files', label: 'Files', href: '/files' }
];

const administratorNavigation: readonly WorkspaceNavigationItem[] = [
  ...dashboardNavigation,
  { id: 'overview', label: 'Administration', href: '/admin' },
  { id: 'connectors', label: 'Connectors', href: '/admin/connectors' },
  { id: 'groupPermissions', label: 'Group permissions', href: '/admin/group-permissions/connectors' },
  { id: 'mcpSetup', label: 'MCP setup guide', href: '/admin/mcp-setup' },
  { id: 'instanceConfiguration', label: 'Instance settings', href: '/admin/instance-configuration' }
];

export function workspaceNavigation(adminAllowed: boolean): readonly WorkspaceNavigationItem[] {
  return adminAllowed ? administratorNavigation : dashboardNavigation;
}
