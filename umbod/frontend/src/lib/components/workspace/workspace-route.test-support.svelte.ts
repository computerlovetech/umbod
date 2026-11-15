export class WorkspaceRoute {
  private currentPath = $state('/dashboard');

  get pathname(): string { return this.currentPath; }
  get inWorkspace(): boolean { return this.currentPath !== '/outside'; }

  navigate = (pathname: string): void => { this.currentPath = pathname; };
}
