import type { LogoutNavigation } from '#lib/admin/infrastructure/logout.js';

import type { SidebarTransition } from '#lib/workspace/navigation-history.svelte.js';
import type { WorkspaceNavigationItem } from '#lib/workspace/navigation.js';
export type { WorkspaceNavigationItem } from '#lib/workspace/navigation.js';

export type AccountMenuLocation = 'sidebar' | 'mobile';

export interface WorkspaceNavigationContext {
  activeItem?: string;
  navigationItems: readonly WorkspaceNavigationItem[];
  destinationPath: string | null;
  originPath: string | null;
  navigationScope?: string;
  hasBackLink?: boolean;
  sidebarTransition?: SidebarTransition;
}

export class WorkspaceShellState {
  #loggingOut = $state(false);
  #openAccountMenu = $state<AccountMenuLocation | null>(null);

  constructor(private readonly context: () => WorkspaceNavigationContext) {}

  get sidebarTransition(): SidebarTransition {
    const context = this.context();
    const entrance = context.hasBackLink ? 'forward' : 'backward';
    return context.sidebarTransition === entrance ? entrance : null;
  }

  get navigationPending(): boolean {
    const context = this.context();
    const scope = context.navigationScope;
    const withinScope = (path: string | null): boolean => !!scope && path !== null && (path === scope || path.startsWith(`${scope}/`));
    if (withinScope(context.originPath) && withinScope(context.destinationPath)) return false;
    return context.destinationPath !== null && context.destinationPath !== context.originPath;
  }

  get pendingNavigationItem(): WorkspaceNavigationItem | undefined {
    const context = this.context();
    if (context.destinationPath === null || context.destinationPath === context.originPath) return undefined;
    return context.navigationItems.find(
      (item) => item.href === context.destinationPath && item.id !== context.activeItem
    );
  }

  get displayedActiveItem(): string | undefined {
    return this.pendingNavigationItem?.id ?? this.context().activeItem;
  }

  get loggingOut(): boolean {
    return this.#loggingOut;
  }

  accountMenuOpen = (location: AccountMenuLocation): boolean => this.#openAccountMenu === location;

  setAccountMenuOpen = (location: AccountMenuLocation, open: boolean): void => {
    if (open || this.accountMenuOpen(location)) this.#openAccountMenu = open ? location : null;
  };

  closeAccountMenu = (): void => {
    this.#openAccountMenu = null;
  };

  logout = async (navigation: LogoutNavigation): Promise<void> => {
    if (this.#loggingOut) return;
    this.#loggingOut = true;
    await navigation.logout();
  };
}
