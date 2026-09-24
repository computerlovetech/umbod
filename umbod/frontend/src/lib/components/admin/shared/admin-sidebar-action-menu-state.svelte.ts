export class AdminSidebarActionMenuState {
  trigger: HTMLButtonElement | null = null;
  menu: HTMLDivElement | null = null;

  setTrigger = (trigger: HTMLButtonElement): void => {
    this.trigger = trigger;
  };

  setMenu = (menu: HTMLDivElement): void => {
    this.menu = menu;
  };

  focusItem = (direction: 'first' | 'last' | 'next' | 'previous'): void => {
    const items = this.focusableItems();
    if (items.length === 0) return;
    const currentIndex = items.findIndex((item) => item === document.activeElement);
    const nextIndex = direction === 'first' ? 0 : direction === 'last' ? items.length - 1 : direction === 'next' ? (currentIndex + 1 + items.length) % items.length : (currentIndex - 1 + items.length) % items.length;
    items[nextIndex]?.focus();
  };

  restoreTriggerFocus = (): void => {
    this.trigger?.focus();
  };

  contains = (target: EventTarget | null): boolean => {
    return target instanceof Node && (this.trigger?.contains(target) === true || this.menu?.contains(target) === true);
  };

  private focusableItems = (): HTMLElement[] => {
    if (this.menu === null) return [];
    return Array.from(this.menu.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled]):not([aria-disabled="true"]), button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled])')).filter((item, index, items) => items.indexOf(item) === index);
  };
}
