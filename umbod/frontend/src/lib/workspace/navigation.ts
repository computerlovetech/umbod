export type WorkspaceNavigationIcon =
  | 'dashboard'
  | 'files'
  | 'gettingStarted'
  | 'settings'
  | 'key'
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

export interface WorkspaceAccountLink {
  label: string;
  href: string;
  icon: WorkspaceNavigationIcon;
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
export const workspaceSettingsHref = '/settings';
export const workspaceTokensHref = `${workspaceSettingsHref}/tokens`;

export const workspaceAccountLinks: readonly WorkspaceAccountLink[] = [
  { label: 'Account settings', href: workspaceSettingsHref, icon: 'settings' },
  { label: 'Access tokens', href: workspaceTokensHref, icon: 'key' }
];

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
export const systemSettingsHref = '/admin/system-settings';
export const agentDiagnosticsHref = '/admin/agent-diagnostics';
export const agentDiagnosticsReportingHref = `${systemSettingsHref}?section=agent-diagnostics`;

export function legacyAgentDiagnosticsTarget(url: URL): string {
  const params = new URLSearchParams(url.search);
  const reporting = params.get('tab') === 'reporting';
  const target = new URL(reporting ? agentDiagnosticsReportingHref : agentDiagnosticsHref, url.origin);
  for (const [name, value] of params) {
    if (name !== 'tab' && (!reporting || name !== 'section')) target.searchParams.append(name, value);
  }
  return `${target.pathname}${target.search}${new URL(url.href).hash}`;
}

export const administrationNavigation: readonly WorkspaceNavigationItem[] = [
  { id: 'connectors', label: 'Connectors', href: '/admin/connectors', icon: 'connectors' },
  { id: 'groups', label: 'Groups', href: '/admin/groups', icon: 'groups' },
  { id: 'namespaces', label: 'Shared namespaces', href: '/admin/namespaces', icon: 'files' },
  { id: 'groupPermissions', label: 'Permissions', href: '/admin/group-permissions/connectors', icon: 'permissions' },
  { id: 'insights', label: 'Insights', href: agentBehaviourFindingsHref, icon: 'analytics' },
  { id: 'agentDiagnostics', label: 'Agent diagnostics', href: agentDiagnosticsHref, icon: 'administration' },
  { id: 'systemSettings', label: 'System settings', href: systemSettingsHref, icon: 'settings' }
];

export const administrationPresentation = {
  ...workspacePresentation,
  workspaceLabel: 'Administration',
  navigationDescription: 'Manage this Umbod instance',
  sidebarLabel: 'Administration sidebar',
  navigationLabel: 'Administration navigation'
};

export function usesWorkspaceShell(pathname: string): boolean {
  return ['/admin', '/dashboard', '/connectors', '/files', '/insights', '/getting-started', workspaceSettingsHref].some((root: string): boolean => pathname === root || pathname.startsWith(`${root}/`));
}

export function workspaceNavigation(adminAllowed: boolean): readonly WorkspaceNavigationItem[] {
  return adminAllowed ? administratorWorkspaceNavigation : dashboardNavigation;
}
