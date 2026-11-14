import { afterEach, expect, test, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import type { ToastApi } from '$lib/components/feedback/toast-state.svelte';
import McpSetupGuide from './McpSetupGuide.svelte';

vi.mock('$lib/components/feedback', () => ({
  useToast: (): ToastApi => ({
    success: (): number => 1, warning: (): number => 1, error: (): number => 1,
    dismiss: (): void => {}
  })
}));

const cleanups: Array<() => Promise<void>> = [];

afterEach(async (): Promise<void> => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  vi.restoreAllMocks();
});

function render(): HTMLDivElement {
  const target = document.createElement('div');
  document.body.append(target);
  const component = mount(McpSetupGuide, {
    target,
    props: {
      installerBaseUrl: 'https://site.test/api/install/v1'
    }
  });
  cleanups.push(async (): Promise<void> => { await unmount(component); target.remove(); });
  flushSync();
  return target;
}

function requiredElement<T extends Element>(target: ParentNode, selector: string): T {
  const element = target.querySelector<T>(selector);
  if (!element) throw new Error(`Missing element ${selector}`);
  return element;
}

test('all OS and harness choices produce copyable shell-specific commands', async (): Promise<void> => {
  const target = render();
  const clipboard = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
  for (const platform of ['macos', 'linux', 'windows']) {
    requiredElement<HTMLButtonElement>(target, `[data-platform="${platform}"]`).click();
    for (const harness of ['codex', 'claude-code']) {
      requiredElement<HTMLInputElement>(target, `input[value="${harness}"]`).click();
      flushSync();
      expect(requiredElement(target, '[role="tab"][aria-selected="true"]').getAttribute('data-platform')).toBe(platform);
      const command = requiredElement<HTMLElement>(target, '.install-card .copyable-value code').textContent;
      expect(command).toContain(platform === 'windows' ? 'irm -MaximumRedirection 0' : 'curl -fsSL');
      expect(command).toContain(`/api/install/v1/${harness}/install.${platform === 'windows' ? 'ps1' : 'sh'}`);
      expect(command?.match(/https?:\/\//g)).toHaveLength(1);
      expect(command).not.toContain('--base-url');
      expect(command).not.toContain('--expected-endpoint');
      requiredElement<HTMLButtonElement>(target, '.install-card .copyable-value button').click();
      await vi.waitFor((): void => expect(clipboard).toHaveBeenLastCalledWith(command));
      const script = requiredElement<HTMLAnchorElement>(target, '.install-links a');
      expect(script.href).toBe(`https://site.test/api/install/v1/${harness}/install.${platform === 'windows' ? 'ps1' : 'sh'}`);
    }
  }
});

test('keyboard tab navigation moves focus and retains harness selection', (): void => {
  const target = render();
  requiredElement<HTMLInputElement>(target, 'input[value="claude-code"]').click();
  flushSync();
  const macos = requiredElement<HTMLButtonElement>(target, '[data-platform="macos"]');
  macos.focus();
  macos.dispatchEvent(new KeyboardEvent('keydown', { key: 'End', bubbles: true, cancelable: true }));
  flushSync();
  const windows = requiredElement<HTMLButtonElement>(target, '[data-platform="windows"]');
  expect(document.activeElement).toBe(windows);
  expect(windows.getAttribute('aria-selected')).toBe('true');
  expect(windows.tabIndex).toBe(0);
  expect(macos.tabIndex).toBe(-1);
  expect(requiredElement<HTMLInputElement>(target, 'input[value="claude-code"]').checked).toBe(true);
  const panel = requiredElement<HTMLElement>(target, '[role="tabpanel"]');
  expect(panel.getAttribute('aria-labelledby')).toBe(windows.id);
  expect(target.textContent).not.toContain('Restart Claude Code');
});

test('both harnesses offer only installation commands without manual or post-install guides', (): void => {
  const target = render();
  for (const harness of ['codex', 'claude-code']) {
    requiredElement<HTMLInputElement>(target, `input[value="${harness}"]`).click();
    flushSync();
    expect(target.textContent).not.toContain('MCP endpoint');
    expect(target.textContent).not.toContain('Manual setup');
    expect(target.textContent).not.toContain('After installation');
    expect(target.textContent).not.toContain('MCP connection only');
    expect(target.textContent).not.toContain('open /mcp');
    expect(target.querySelector('details')).toBeNull();
    expect(target.querySelector('a[download]')).toBeNull();
    expect(target.querySelector('.connection-card')).toBeNull();
    expect(target.querySelector('.next-step')).toBeNull();
  }
});
