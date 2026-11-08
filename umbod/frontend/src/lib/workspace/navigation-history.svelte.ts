import { usesWorkspaceShell } from './navigation';

export type SidebarTransition = 'forward' | 'backward' | null;

function isAdministration(pathname: string): boolean {
  return pathname === '/admin' || pathname.startsWith('/admin/');
}

export class WorkspaceNavigationHistory {
  #returnHref = $state('/dashboard');
  #transition = $state<SidebarTransition>(null);
  readonly #origin: string;

  constructor(initialUrl: URL, successful: boolean) {
    this.#origin = initialUrl.origin;
    this.completeNavigation(initialUrl, successful);
  }

  get returnHref(): string {
    return this.#returnHref;
  }

  get transition(): SidebarTransition {
    return this.#transition;
  }

  startNavigation = (from: URL | null, to: URL | null, sourceSuccessful: boolean): void => {
    this.#transition = null;
    if (from !== null) this.completeNavigation(from, sourceSuccessful);
    if (from === null || to === null || from.origin !== this.#origin || to.origin !== this.#origin) return;
    if (!usesWorkspaceShell(from.pathname) || !usesWorkspaceShell(to.pathname)) return;
    if (isAdministration(from.pathname) === isAdministration(to.pathname)) return;
    this.#transition = isAdministration(to.pathname) ? 'forward' : 'backward';
  };

  completeNavigation = (url: URL, successful: boolean): void => {
    if (!successful) {
      this.#transition = null;
      return;
    }
    if (url.origin !== this.#origin || !usesWorkspaceShell(url.pathname) || isAdministration(url.pathname)) return;
    this.#returnHref = `${url.pathname}${url.search}${url.hash}`;
  };
}
