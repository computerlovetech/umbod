export class WorkspaceNavigationState {
  constructor(private readonly pathname: () => string) {}

  get activeItem(): string | undefined {
    const path = this.pathname();
    if (path === '/getting-started' || path.startsWith('/getting-started/')) return 'gettingStarted';
    if (path === '/files' || path.startsWith('/files/')) return 'files';
    if (path === '/insights' || path.startsWith('/insights/')) return 'insights';
    if (path === '/connectors' || path.startsWith('/connectors/')) return 'connectors';
    if (path === '/dashboard' || path.startsWith('/dashboard/')) return 'dashboard';
    return undefined;
  }
}
