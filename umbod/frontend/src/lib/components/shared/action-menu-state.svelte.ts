import { tick } from 'svelte';

export class ActionMenuState {
  trigger: HTMLButtonElement | null = null;
  menu: HTMLDivElement | null = null;

  triggerKeydown = (event: KeyboardEvent, onopenchange: (open: boolean) => void): void => {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
    event.preventDefault();
    onopenchange(true);
    void tick().then(() => this.focusItem(event.key === 'ArrowDown' ? 'first' : 'last'));
  };

  menuKeydown = (event: KeyboardEvent, onopenchange: (open: boolean) => void): void => {
    if (event.key === 'Tab') { onopenchange(false); return; }
    if (event.key === 'Escape') {
      event.preventDefault();
      onopenchange(false);
      queueMicrotask(this.restoreTriggerFocus);
      return;
    }
    const direction = event.key === 'ArrowDown' ? 'next' : event.key === 'ArrowUp' ? 'previous' : event.key === 'Home' ? 'first' : event.key === 'End' ? 'last' : null;
    if (direction === null) return;
    event.preventDefault();
    this.focusItem(direction);
  };

  outsideClick = (event: MouseEvent, open: boolean, onopenchange: (open: boolean) => void): void => {
    if (!open || this.contains(event.target)) return;
    onopenchange(false);
  };

  attachMenu = (menu: HTMLDivElement): (() => void) => {
    this.menu = menu;
    this.positionMenu();
    const observer = typeof ResizeObserver === 'undefined' ? undefined : new ResizeObserver(this.positionMenu);
    observer?.observe(menu);
    return () => {
      observer?.disconnect();
      if (this.menu === menu) this.menu = null;
    };
  };

  positionMenu = (): void => {
    if (!this.trigger || !this.menu) return;
    const rect = this.trigger.getBoundingClientRect();
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - this.menu.offsetWidth - 8));
    const top = Math.max(8, Math.min(rect.bottom + 4, window.innerHeight - this.menu.offsetHeight - 8));
    this.menu.style.left = `${left}px`;
    this.menu.style.top = `${top}px`;
    this.menu.style.maxHeight = `${Math.max(0, Math.min(window.innerHeight * 0.6, window.innerHeight - top - 8))}px`;
  };

  setTrigger = (trigger: HTMLButtonElement): void => {
    this.trigger = trigger;
  };

  setMenu = (menu: HTMLDivElement): void => {
    this.menu = menu;
  };

  focusItem = (direction: 'first' | 'last' | 'next' | 'previous'): void => {
    const items = this.focusableItems();
    if (items.length === 0) { this.menu?.focus(); return; }
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
