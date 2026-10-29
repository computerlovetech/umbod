import { Window } from 'happy-dom';
import { afterEach, describe, expect, test, vi } from 'vitest';
import { render } from 'svelte/server';
import { ActionMenuState } from './action-menu-state.svelte';
import { AdminSidebarActionMenuState } from '$lib/components/admin/shared/admin-sidebar-action-menu-state.svelte';
import AdminSidebarActionMenu from '$lib/components/admin/shared/AdminSidebarActionMenu.svelte';

function fixture(): { state: ActionMenuState; window: Window; first: HTMLAnchorElement; last: HTMLButtonElement } {
  const window = new Window();
  vi.stubGlobal('window', window);
  vi.stubGlobal('document', window.document);
  vi.stubGlobal('Node', window.Node);
  window.document.body.innerHTML = '<button id="trigger">Folders</button><div id="menu"><a role="menuitem" href="/files?node=first">First</a><button role="menuitem" disabled>Unavailable</button><button role="menuitem">Last</button></div><button id="outside">Outside</button>';
  const state = new ActionMenuState();
  state.setTrigger(document.querySelector<HTMLButtonElement>('#trigger')!);
  state.setMenu(document.querySelector<HTMLDivElement>('#menu')!);
  return { state, window, first: document.querySelector<HTMLAnchorElement>('a')!, last: document.querySelector<HTMLButtonElement>('#menu button:last-child')! };
}

afterEach((): void => { vi.unstubAllGlobals(); });

describe('neutral controlled menu mechanics', () => {
  test.each([['ArrowDown', 'first'], ['ArrowUp', 'last']])('keyboard opening with %s focuses %s', async (key, position): Promise<void> => {
    const { state, window, first, last } = fixture();
    const change = vi.fn();
    const event = new window.KeyboardEvent('keydown', { key, cancelable: true });
    state.triggerKeydown(event as unknown as KeyboardEvent, change);
    await Promise.resolve();
    expect(change).toHaveBeenCalledWith(true);
    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(position === 'first' ? first : last);
  });

  test('arrows wrap, Home and End move, and disabled items are skipped', (): void => {
    const { state, window, first, last } = fixture();
    const change = vi.fn();
    first.focus();
    for (const [key, target] of [['ArrowDown', last], ['ArrowDown', first], ['ArrowUp', last], ['Home', first], ['End', last]] as const) {
      state.menuKeydown(new window.KeyboardEvent('keydown', { key }) as unknown as KeyboardEvent, change);
      expect(document.activeElement).toBe(target);
    }
    expect(change).not.toHaveBeenCalled();
  });

  test('Escape restores trigger focus and Tab closes without trapping native focus movement', async (): Promise<void> => {
    const { state, window, first } = fixture();
    const change = vi.fn();
    first.focus();
    state.menuKeydown(new window.KeyboardEvent('keydown', { key: 'Escape' }) as unknown as KeyboardEvent, change);
    await Promise.resolve();
    expect(change).toHaveBeenLastCalledWith(false);
    expect(document.activeElement).toBe(state.trigger);
    first.focus();
    const tab = new window.KeyboardEvent('keydown', { key: 'Tab', cancelable: true });
    state.menuKeydown(tab as unknown as KeyboardEvent, change);
    expect(tab.defaultPrevented).toBe(false);
    expect(document.activeElement).toBe(first);
  });

  test.each(['button', 'input'])('outside clicks preserve the clicked %s focus while internal and closed-menu clicks do not close', (tag): void => {
    const { state, window, first } = fixture();
    const change = vi.fn();
    const inside = new window.MouseEvent('click');
    first.dispatchEvent(inside as unknown as Event);
    state.outsideClick(inside as unknown as MouseEvent, true, change);
    expect(change).not.toHaveBeenCalled();
    const target = document.createElement(tag);
    document.body.append(target);
    target.focus();
    const outside = new window.MouseEvent('click');
    target.dispatchEvent(outside as unknown as Event);
    state.outsideClick(outside as unknown as MouseEvent, false, change);
    expect(change).not.toHaveBeenCalled();
    state.outsideClick(outside as unknown as MouseEvent, true, change);
    expect(change).toHaveBeenCalledWith(false);
    expect(document.activeElement).toBe(target);
  });

  test('loading or empty menus receive keyboard focus and positioned menus stay within the viewport', (): void => {
    const { state } = fixture();
    state.menu!.replaceChildren();
    state.menu!.tabIndex = -1;
    state.focusItem('first');
    expect(document.activeElement).toBe(state.menu);
    const cleanup = state.attachMenu(state.menu!);
    expect(Number.parseFloat(state.menu!.style.left)).toBeGreaterThanOrEqual(8);
    expect(Number.parseFloat(state.menu!.style.top)).toBeGreaterThanOrEqual(8);
    cleanup();
    expect(state.menu).toBeNull();
  });

  test('administration keeps the same state class and controlled trigger semantics', (): void => {
    expect(AdminSidebarActionMenuState).toBe(ActionMenuState);
    const body = render(AdminSidebarActionMenu, { props: { open: false, label: 'Connector actions', menu: vi.fn(), onopenchange: vi.fn() } }).body;
    expect(body).toContain('aria-label="Connector actions"');
    expect(body).toContain('aria-haspopup="menu"');
    expect(body).toContain('aria-expanded="false"');
    expect(body).toContain('⋯');
    expect(body).not.toContain('role="menu"');
  });
});
