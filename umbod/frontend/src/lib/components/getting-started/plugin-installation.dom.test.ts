import { afterEach, expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import McpSetupGuide from './McpSetupGuide.svelte';
import { InMemoryTelemetryInstallClaims } from '#lib/telemetry-setup/in-memory-api.test-support.js';

const cleanups: Array<() => Promise<void>> = [];

afterEach(async (): Promise<void> => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function render(installClaims?: InMemoryTelemetryInstallClaims): HTMLDivElement {
  const target = document.createElement('div');
  document.body.append(target);
  const component = mount(McpSetupGuide, {
    target,
    props: { installerBaseUrl: 'https://site.test/api/install/v1', installClaims }
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

function press(target: ParentNode, name: string): void {
  const control = Array.from(target.querySelectorAll('button')).find((button) => button.textContent?.trim() === name);
  if (!control) throw new Error(`Missing button ${name}`);
  control.click();
  flushSync();
}

function visit(target: ParentNode, name: string): void {
  const nav = requiredElement(target, '[aria-label="Installer steps"]');
  const control = Array.from(nav.querySelectorAll('button')).find((button) => button.querySelector('span:last-child')?.firstChild?.textContent === name);
  if (!control) throw new Error(`Missing wizard step ${name}`);
  control.click();
  flushSync();
}

function select(target: ParentNode, value: string): void {
  const radio = requiredElement<HTMLInputElement>(target, `input[type="radio"][value="${value}"]`);
  radio.click();
  flushSync();
  expect(radio.checked).toBe(true);
}

function chooseLogs(target: ParentNode, harness: string): void {
  visit(target, 'Harness');
  select(target, harness);
  visit(target, 'Telemetry');
  select(target, 'logs');
}

test('uses native radio cards and focuses the step heading on Continue, Back and sidebar navigation', async (): Promise<void> => {
  const target = render();
  for (const icon of ['apple', 'linux', 'windows']) {
    expect(requiredElement(target, `label img[src="/icons/${icon}.svg"]`).getAttribute('alt')).toBe('');
  }
  select(target, 'linux');
  press(target, 'Continue');
  await vi.waitFor((): void => expect(document.activeElement?.textContent).toBe('Choose your harness'));
  for (const icon of ['codex.png', 'claude-code.svg']) {
    expect(requiredElement(target, `label img[src="/icons/${icon}"]`).getAttribute('alt')).toBe('');
  }
  select(target, 'claude-code');
  press(target, 'Back');
  await tick();
  expect(document.activeElement?.textContent).toBe('Choose your platform');
  expect(requiredElement<HTMLInputElement>(target, 'input[value="linux"]').checked).toBe(true);
  visit(target, 'Harness');
  await tick();
  expect(document.activeElement?.textContent).toBe('Choose your harness');
  expect(requiredElement<HTMLInputElement>(target, 'input[value="claude-code"]').checked).toBe(true);
  expect(requiredElement(target, '[aria-current="step"]').textContent).toContain('Claude Code');
});

test.each([
  ['macos', 'codex', 'curl -fsSL', 'sh', 'Terminal'],
  ['linux', 'claude-code', 'curl -fsSL', 'sh', 'Bash · includes WSL'],
  ['windows', 'claude-code', 'irm -MaximumRedirection 0', 'ps1', 'PowerShell']
])('shows the complete standard command immediately for %s and %s', async (platform, harness, prefix, extension, shell): Promise<void> => {
  const target = render();
  const clipboard = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
  select(target, platform);
  press(target, 'Continue');
  select(target, harness);
  press(target, 'Continue');
  expect(requiredElement(target, '[aria-current="step"]').textContent).toContain('Review and install');
  expect(requiredElement(target, '[aria-label="Installer steps"]').textContent).not.toContain('Telemetry');
  expect(target.textContent).toContain('Step 3 of 3');
  expect(target.textContent).not.toContain('Without telemetry');
  press(target, 'Back');
  expect(requiredElement(target, '[aria-current="step"]').textContent).toContain('Harness');
  press(target, 'Continue');
  const scriptUrl = `https://site.test/api/install/v1/${harness}/install.${extension}`;
  const command = requiredElement(target, 'code').textContent;
  expect(command).toContain(prefix);
  expect(command).toContain(scriptUrl);
  expect(command?.match(/https?:\/\//g)).toHaveLength(1);
  expect(command).not.toContain('--base-url');
  expect(command).not.toContain('--expected-endpoint');
  const card = requiredElement(target, '.install-card');
  expect(card.textContent).toContain(`Install command${shell}`);
  expect(card.textContent).not.toMatch(/Requires|Inspect installer|Installer preview|10 minutes|Show full command/);
  expect(card.querySelector('a')).toBeNull();
  press(card, 'Copy command');
  await vi.waitFor((): void => expect(card.textContent).toContain('Copied'));
  expect(clipboard).toHaveBeenCalledExactlyOnceWith(command);
});

test.each([
  ['macos', 'codex', 'sh'],
  ['linux', 'claude-code', 'sh'],
  ['windows', 'claude-code', 'ps1']
])('copies a single telemetry install command on demand for %s and %s', async (platform, harness, extension): Promise<void> => {
  const claims = new InMemoryTelemetryInstallClaims();
  const clipboard = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
  const target = render(claims);
  select(target, platform);
  visit(target, 'Telemetry');
  expect(requiredElement<HTMLInputElement>(target, 'input[value="skip"]').checked).toBe(true);
  press(target, 'Continue');
  expect(requiredElement(target, 'code').textContent).not.toContain(claims.code);
  chooseLogs(target, harness);
  expect(target.textContent).not.toContain('Copy command');
  press(target, 'Continue');
  const preview = requiredElement(target, 'code').textContent;
  expect(preview).toContain('••••');
  expect(target.textContent).toContain('Use once within 10 minutes.');
  expect(target.textContent).not.toContain('Show full command');
  expect(target.innerHTML).not.toContain(claims.code);
  expect(claims.requests).toEqual([]);
  expect(clipboard).not.toHaveBeenCalled();
  press(target, 'Copy command');
  expect(requiredElement(target, '[role="status"]').textContent).toContain('Preparing');
  await vi.waitFor((): void => expect(target.textContent).toContain('Copied'));
  expect(claims.requests.map(({ request }) => request)).toEqual([{ harness }]);
  const command = clipboard.mock.calls[0]?.[0];
  expect(command).toContain(`https://site.test/api/install/v1/${harness}/install.${extension}`);
  expect(command).toContain(claims.code);
  expect(command?.split('\n')).toHaveLength(1);
  expect(clipboard).toHaveBeenCalledExactlyOnceWith(command);
  expect(preview).toBe(command?.replace(claims.code, '••••••••••••••••'));
  expect(target.innerHTML).not.toContain(claims.code);
  press(target, 'Show full command');
  expect(requiredElement(target, 'code').textContent).toBe(command);
  expect(requiredElement(target, 'button[aria-pressed]').getAttribute('aria-pressed')).toBe('true');
  press(target, 'Hide setup code');
  expect(requiredElement(target, 'code').textContent).toBe(preview);
  expect(target.innerHTML).not.toContain(claims.code);
  press(target, 'Copied');
  await tick();
  expect(claims.requests).toHaveLength(1);
  expect(clipboard).toHaveBeenCalledTimes(2);
});

test('shows a selectable command after clipboard failure and reports preparation errors without leaking details', async (): Promise<void> => {
  const claims = new InMemoryTelemetryInstallClaims();
  claims.beforeCreate = async (): Promise<void> => { throw new Error('sensitive response detail'); };
  vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('clipboard denied'));
  const target = render(claims);
  chooseLogs(target, 'codex');
  press(target, 'Continue');
  press(target, 'Copy command');
  await vi.waitFor((): void => expect(requiredElement(target, '[role="alert"]').textContent).toBe('Could not prepare your install command.'));
  expect(target.textContent).not.toContain('sensitive response detail');
  expect(requiredElement(target, 'code').textContent).toContain('••••');
  claims.beforeCreate = async (): Promise<void> => {};
  press(target, 'Copy command');
  await vi.waitFor((): void => expect(requiredElement(target, '[role="status"]').textContent).toContain('Clipboard unavailable.'));
  expect(requiredElement(target, 'code').textContent).toContain(claims.code);
  press(target, 'Reset command');
  expect(target.innerHTML).not.toContain(claims.code);
  expect(target.textContent).not.toMatch(/Clipboard unavailable|Show full command|Hide setup code/);
});

test('discards an outstanding claim when the user leaves Review', async (): Promise<void> => {
  const claims = new InMemoryTelemetryInstallClaims();
  const pending = Promise.withResolvers<void>();
  claims.beforeCreate = () => pending.promise;
  const clipboard = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
  const target = render(claims);
  chooseLogs(target, 'claude-code');
  press(target, 'Continue');
  press(target, 'Copy command');
  press(target, 'Copy command');
  expect(claims.requests).toHaveLength(1);
  press(target, 'Back');
  expect(claims.requests[0]?.signal.aborted).toBe(true);
  pending.resolve();
  await pending.promise;
  await tick();
  press(target, 'Continue');
  expect(claims.requests).toHaveLength(1);
  expect(clipboard).not.toHaveBeenCalled();
  expect(requiredElement(target, 'code').textContent).toContain('••••');
  expect(target.innerHTML).not.toContain(claims.code);
});

test('clears copy feedback and expires a revealed claim before generating a masked replacement', async (): Promise<void> => {
  vi.useFakeTimers();
  const claims = new InMemoryTelemetryInstallClaims();
  const clipboard = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
  const target = render(claims);
  chooseLogs(target, 'codex');
  press(target, 'Continue');
  press(target, 'Copy command');
  await vi.waitFor((): void => expect(target.textContent).toContain('Copied'));
  press(target, 'Show full command');
  const originalCode = claims.code;
  expect(requiredElement(target, 'code').textContent).toContain(originalCode);
  await vi.advanceTimersByTimeAsync(2_000);
  expect(target.textContent).toContain('Copy command');
  expect(target.textContent).not.toContain('Copied');
  await vi.advanceTimersByTimeAsync(10 * 60_000 - 2_000);
  expect(target.innerHTML).not.toContain(originalCode);
  expect(target.textContent).not.toMatch(/Show full command|Hide setup code|Reset command/);
  expect(requiredElement(target, '[role="status"]').textContent).toContain('expired');
  claims.code = 'B'.repeat(43);
  press(target, 'Generate new command');
  await vi.waitFor((): void => expect(target.textContent).toContain('Copied'));
  expect(claims.requests).toHaveLength(2);
  expect(clipboard.mock.lastCall?.[0]).toContain(claims.code);
  expect(target.innerHTML).not.toContain(claims.code);
  press(target, 'Show full command');
  expect(requiredElement(target, 'code').textContent).toContain(claims.code);
  press(target, 'Back');
  press(target, 'Continue');
  expect(target.innerHTML).not.toContain(claims.code);
  expect(target.textContent).not.toContain('Show full command');
});
