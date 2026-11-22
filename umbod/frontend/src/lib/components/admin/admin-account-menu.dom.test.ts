import { afterEach, expect, test, vi } from 'vitest';
import { createRawSnippet, mount, tick, unmount } from 'svelte';
import AdminShell from './AdminShell.svelte';

vi.mock('$app/state', () => ({ navigating: { to: null, from: null } }));

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

test.each(['aside', '.mobile-workspace-bar'])('account actions open by keyboard and click from %s', async (region): Promise<void> => {
  const logout = vi.fn<() => Promise<void>>().mockResolvedValue();
  component = mount(AdminShell, { target: document.body, props: {
    activeItem: 'connectors',
    accountIdentity: { kind: 'visible', name: 'Admin', email: 'admin@example.test', picture: null, hiddenValues: { id: 'admin' } },
    logout: { logout },
    children: createRawSnippet(() => ({ render: (): string => '<p>Content</p>' }))
  } });
  await tick();
  const account = document.querySelector<HTMLButtonElement>(`${region} button[aria-label="Admin account menu"]`);
  expect(account).not.toBeNull();
  expect(document.querySelector('.mobile-workspace-bar button[aria-label="Open workspace menu"]')).not.toBeNull();
  expect(document.querySelector('[role="menu"]')).toBeNull();

  account!.focus();
  account!.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
  await tick();
  await Promise.resolve();
  expect(account!.getAttribute('aria-expanded')).toBe('true');
  const popup = document.getElementById(account!.getAttribute('aria-controls')!);
  const settings = popup?.querySelector('a[href="/settings"]');
  const tokens = popup?.querySelector('a[href="/settings/tokens"]');
  expect(settings?.textContent?.trim()).toBe('Account settings');
  expect(tokens?.textContent?.trim()).toBe('Access tokens');
  expect(document.activeElement).toBe(settings);
  settings!.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
  expect(document.activeElement).toBe(tokens);
  tokens!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  await tick();
  expect(document.activeElement).toBe(account);
  expect(document.querySelector('[role="menu"]')).toBeNull();

  account!.click();
  await tick();
  expect(account!.getAttribute('aria-expanded')).toBe('true');
  document.body.click();
  await tick();
  expect(account!.getAttribute('aria-expanded')).toBe('false');
  expect(logout).not.toHaveBeenCalled();
});

test.each([true, false])('switching responsive navigation modes with popover support %s', async (supportsPopover: boolean): Promise<void> => {
  const query = window.matchMedia('(max-width: 720px)');
  vi.spyOn(window, 'matchMedia').mockReturnValue(query);
  const mobile = vi.spyOn(query, 'matches', 'get').mockReturnValue(false);
  const previous = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'hidePopover');
  Object.defineProperty(HTMLElement.prototype, 'hidePopover', { configurable: true, value: supportsPopover ? vi.fn<() => void>() : undefined });
  try {
    component = mount(AdminShell, { target: document.body, props: {
      activeItem: 'connectors',
      accountIdentity: { kind: 'hidden' },
      children: createRawSnippet(() => ({ render: (): string => '<p>Content</p>' }))
    } });
    await tick();
    const sidebar = document.querySelector('aside');
    const account = sidebar?.querySelector<HTMLButtonElement>('button[aria-haspopup="menu"]');
    account?.click();
    await tick();
    expect(account?.getAttribute('aria-expanded')).toBe('true');

    mobile.mockReturnValue(true);
    query.dispatchEvent(new Event('change'));
    await tick();
    expect(sidebar?.hasAttribute('popover')).toBe(supportsPopover);
    expect(account?.getAttribute('aria-expanded')).toBe(String(!supportsPopover));
    expect(document.querySelector('[role="menu"]') === null).toBe(supportsPopover);
  } finally {
    if (previous) Object.defineProperty(HTMLElement.prototype, 'hidePopover', previous);
    else Reflect.deleteProperty(HTMLElement.prototype, 'hidePopover');
  }
});
