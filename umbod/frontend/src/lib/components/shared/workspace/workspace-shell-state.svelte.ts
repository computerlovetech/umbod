import type { LogoutNavigation } from '$lib/admin/infrastructure/logout';

import type { WorkspaceNavigationItem } from '$lib/workspace/navigation';
export type { WorkspaceNavigationItem } from '$lib/workspace/navigation';

export interface WorkspaceNavigationContext {
  activeItem: string;
  navigationItems: readonly WorkspaceNavigationItem[];
  destinationPath: string | null;
  originPath: string | null;
  navigationScope?: string;
}

export class WorkspaceShellState {
  loggingOut = $state(false);

  constructor(private readonly context: () => WorkspaceNavigationContext) {}

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

  get displayedActiveItem(): string {
    return this.pendingNavigationItem?.id ?? this.context().activeItem;
  }

  logout = async (navigation: LogoutNavigation): Promise<void> => {
    if (this.loggingOut) return;
    this.loggingOut = true;
    await navigation.logout();
  };
}
