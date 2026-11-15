export class WorkspaceNavigationState {
  constructor(private readonly pathname: () => string) {}

  get activeItem(): string {
    const path = this.pathname();
    if (path === '/getting-started' || path.startsWith('/getting-started/')) return 'gettingStarted';
    if (path === '/files' || path.startsWith('/files/')) return 'files';
    if (path === '/connectors' || path.startsWith('/connectors/')) return 'connectors';
    return 'dashboard';
  }
}
