import { tick } from 'svelte';

const viewportInset = 8;
const triggerGap = 4;

export class ActionMenuState {
  constructor(private readonly alignment: () => 'start' | 'end' = () => 'start') {}
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
    const width = this.menu.offsetWidth;
    const desiredLeft = this.alignment() === 'end' ? rect.right - width : rect.left;
    const left = Math.max(viewportInset, Math.min(desiredLeft, window.innerWidth - width - viewportInset));
    const heightLimit = window.innerHeight * 0.6;
    const borderHeight = this.menu.offsetHeight - this.menu.clientHeight;
    const preferredHeight = Math.min(heightLimit, this.menu.scrollHeight + borderHeight);
    const belowTop = Math.max(viewportInset, rect.bottom + triggerGap);
    const aboveBottom = Math.min(window.innerHeight - viewportInset, rect.top - triggerGap);
    const below = window.innerHeight - belowTop - viewportInset;
    const above = aboveBottom - viewportInset;
    const opensUpward = preferredHeight > below && above > below;
    const maxHeight = Math.max(0, Math.min(heightLimit, opensUpward ? above : below));
    this.menu.style.left = `${left}px`;
    this.menu.style.maxHeight = `${maxHeight}px`;
    this.menu.style.top = `${opensUpward ? aboveBottom - this.menu.offsetHeight : belowTop}px`;
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
