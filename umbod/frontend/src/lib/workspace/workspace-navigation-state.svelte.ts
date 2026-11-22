import { workspaceSettingsHref } from './navigation.js';

export class WorkspaceNavigationState {
  constructor(private readonly pathname: () => string) {}

  get activeItem(): string {
    const path = this.pathname();
    if (path === workspaceSettingsHref || path.startsWith(`${workspaceSettingsHref}/`)) return 'settings';
    if (path === '/getting-started' || path.startsWith('/getting-started/')) return 'gettingStarted';
    if (path === '/files' || path.startsWith('/files/')) return 'files';
    if (path === '/insights' || path.startsWith('/insights/')) return 'insights';
    if (path === '/connectors' || path.startsWith('/connectors/')) return 'connectors';
    return 'dashboard';
  }
}
