export type WorkspaceNavigationIcon =
  | 'dashboard'
  | 'files'
  | 'gettingStarted'
  | 'administration'
  | 'connectors'
  | 'groups'
  | 'permissions'
  | 'analytics';

export interface WorkspaceNavigationItem {
  id: string;
  label: string;
  href: string;
  icon?: WorkspaceNavigationIcon;
  startsSection?: boolean;
}

export const workspacePresentation = {
  workspaceLabel: 'Workspace',
  homeHref: '/dashboard',
  accountFallback: 'Your account',
  sidebarLabel: 'Workspace sidebar',
  navigationLabel: 'Workspace navigation'
};

export const personalInsightsHref = '/insights/agent-behaviour';
export const personalInsightsLogsHref = '/insights/logs';

const dashboardNavigation: readonly WorkspaceNavigationItem[] = [
  { id: 'dashboard', label: 'Dashboard', href: '/dashboard', icon: 'dashboard' },
  { id: 'connectors', label: 'Connectors', href: '/connectors', icon: 'connectors' },
  { id: 'files', label: 'Files', href: '/files', icon: 'files' },
  { id: 'insights', label: 'Insights', href: personalInsightsHref, icon: 'analytics' },
  { id: 'gettingStarted', label: 'Getting started', href: '/getting-started', icon: 'gettingStarted' }
];

const administratorWorkspaceNavigation: readonly WorkspaceNavigationItem[] = [
  ...dashboardNavigation,
  { id: 'administration', label: 'Administration', href: '/admin/connectors', icon: 'administration', startsSection: true }
];

export const agentBehaviourFindingsHref = '/admin/insights/agent-behaviour';
export const agentDiagnosticsHref = '/admin/agent-diagnostics';

export const administrationNavigation: readonly WorkspaceNavigationItem[] = [
  { id: 'connectors', label: 'Connectors', href: '/admin/connectors', icon: 'connectors' },
  { id: 'groups', label: 'Groups', href: '/admin/groups', icon: 'groups' },
  { id: 'namespaces', label: 'Shared namespaces', href: '/admin/namespaces', icon: 'files' },
  { id: 'groupPermissions', label: 'Permissions', href: '/admin/group-permissions/connectors', icon: 'permissions' },
  { id: 'insights', label: 'Insights', href: agentBehaviourFindingsHref, icon: 'analytics' },
  { id: 'agentDiagnostics', label: 'Agent diagnostics', href: agentDiagnosticsHref, icon: 'administration' }
];

export const administrationPresentation = {
  ...workspacePresentation,
  workspaceLabel: 'Administration',
  navigationDescription: 'Manage this Umbod instance',
  sidebarLabel: 'Administration sidebar',
  navigationLabel: 'Administration navigation'
};

export function usesWorkspaceShell(pathname: string): boolean {
  return ['/admin', '/dashboard', '/connectors', '/files', '/insights', '/getting-started'].some((root: string): boolean => pathname === root || pathname.startsWith(`${root}/`));
}

export function workspaceNavigation(adminAllowed: boolean): readonly WorkspaceNavigationItem[] {
  return adminAllowed ? administratorWorkspaceNavigation : dashboardNavigation;
}
