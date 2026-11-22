import { afterEach, expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import type { ToastApi } from '#lib/components/feedback/toast-state.svelte.js';
import McpSetupGuide from './McpSetupGuide.svelte';
import type { TelemetryInstaller } from './telemetry-installer';

vi.mock('#lib/components/feedback/index.js', () => ({
  useToast: (): ToastApi => ({
    success: (): number => 1, warning: (): number => 1, error: (): number => 1,
    dismiss: (): void => {}
  })
}));

const cleanups: Array<() => Promise<void>> = [];

afterEach(async (): Promise<void> => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function render(telemetryInstaller?: TelemetryInstaller): HTMLDivElement {
  const target = document.createElement('div');
  document.body.append(target);
  const component = mount(McpSetupGuide, {
    target,
    props: { installerBaseUrl: 'https://site.test/api/install/v1', telemetryInstaller }
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

function chooseLogs(target: ParentNode): void {
  visit(target, 'Harness');
  select(target, 'claude-code');
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
  ['macos', 'codex', 'curl -fsSL', 'sh', 'Python 3.8+ and curl', 'https://developers.openai.com/codex/plugins'],
  ['linux', 'claude-code', 'curl -fsSL', 'sh', 'Python 3.8+ and curl', 'https://code.claude.com/docs/en/plugins'],
  ['windows', 'claude-code', 'irm -MaximumRedirection 0', 'ps1', 'PowerShell 5.1+', 'https://code.claude.com/docs/en/plugins']
])('offers the copyable standard installer and docs for %s with %s', async (platform, harness, prefix, extension, requires, docs): Promise<void> => {
  const target = render();
  const clipboard = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
  select(target, platform);
  press(target, 'Continue');
  select(target, harness);
  press(target, 'Continue');
  expect(requiredElement(target, '[aria-current="step"]').textContent).toContain('Review and install');
  expect(requiredElement(target, '[aria-label="Installer steps"]').textContent).not.toContain('Telemetry');
  expect(target.textContent).toContain('Step 3 of 3');
  expect(target.textContent).not.toContain('Skip telemetry');
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
  expect(target.textContent).toContain(requires);
  expect(target.textContent).toContain('No administrator access required.');
  expect(target.textContent).not.toContain('Manual setup');
  requiredElement(target, `a[href="${scriptUrl}"]`);
  requiredElement(target, `a[href="${docs}"]`);
  requiredElement<HTMLButtonElement>(target, '.copyable-value button').click();
  await vi.waitFor((): void => expect(clipboard).toHaveBeenCalledWith(command));
});

test('never prepares a package for Codex or on skip, even when a telemetry installer is available', (): void => {
  const prepare = vi.fn<TelemetryInstaller['prepare']>();
  const target = render({ prepare });
  visit(target, 'Telemetry');
  expect(target.querySelector('input[value="logs"]')).toBeNull();
  const tomlLink = 'a[href="/settings/tokens"]';
  expect(requiredElement(target, tomlLink).textContent).toContain('Generate Codex telemetry TOML');
  expect(target.textContent).toContain('Step 3 of 4');
  visit(target, 'Review and install');
  expect(prepare).not.toHaveBeenCalled();
  visit(target, 'Harness');
  select(target, 'claude-code');
  visit(target, 'Telemetry');
  expect(requiredElement<HTMLInputElement>(target, 'input[value="skip"]').checked).toBe(true);
  expect(target.querySelector(tomlLink)).toBeNull();
  visit(target, 'Review and install');
  expect(prepare).not.toHaveBeenCalled();
});

test('prepares once on Review and downloads the Blob only on click without displaying the private script', async (): Promise<void> => {
  const blob = new Blob(['private script body']);
  const prepare = vi.fn<TelemetryInstaller['prepare']>().mockResolvedValue(blob);
  const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:private');
  const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation((): void => {});
  const download = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement): void {
    expect(this.download).toBe('umbod-installer.zip');
    expect(this.href).toBe('blob:private');
  });
  const target = render({ prepare });
  select(target, 'windows');
  chooseLogs(target);
  expect(prepare).not.toHaveBeenCalled();
  press(target, 'Continue');
  expect(prepare).toHaveBeenCalledWith('windows', 'claude-code', expect.any(AbortSignal));
  expect(requiredElement(target, '[role="status"]').textContent).toContain('Preparing');
  visit(target, 'Review and install');
  await vi.waitFor((): void => expect(target.textContent).toContain('Keep the ZIP and extracted files private. Delete them after use.'));
  press(target, 'Back');
  visit(target, 'Review and install');
  expect(prepare).toHaveBeenCalledTimes(1);
  expect(target.textContent).not.toContain('private script body');
  expect(requiredElement(target, 'code').textContent).toBe('.\\umbod-install.ps1');
  expect(target.querySelector('a[download]')).toBeNull();
  expect(create).not.toHaveBeenCalled();
  vi.useFakeTimers();
  press(target, 'Download installer');
  expect(create).toHaveBeenCalledWith(blob);
  expect(download).toHaveBeenCalledTimes(1);
  await vi.runAllTimersAsync();
  expect(revoke).toHaveBeenCalledWith('blob:private');
});

test('reports a generic package failure and retries only after an explicit click', async (): Promise<void> => {
  const prepare = vi.fn<TelemetryInstaller['prepare']>()
    .mockRejectedValueOnce(new Error('sensitive response detail'))
    .mockResolvedValueOnce(new Blob(['private script']));
  const target = render({ prepare });
  chooseLogs(target);
  press(target, 'Continue');
  await vi.waitFor((): void => expect(requiredElement(target, '[role="alert"]').textContent).toBe('Could not prepare your installer.'));
  expect(target.textContent).not.toContain('sensitive response detail');
  press(target, 'Back');
  press(target, 'Continue');
  expect(prepare).toHaveBeenCalledTimes(1);
  press(target, 'Retry');
  await vi.waitFor((): void => expect(target.textContent).toContain('Download installer'));
  expect(prepare).toHaveBeenCalledTimes(2);
});

test('switching to Codex aborts an outstanding package and clears the telemetry choice', async (): Promise<void> => {
  let resolvePackage: (blob: Blob) => void = (): void => {};
  const pending = new Promise<Blob>((resolve): void => { resolvePackage = resolve; });
  const prepare = vi.fn<TelemetryInstaller['prepare']>().mockReturnValue(pending);
  const target = render({ prepare });
  chooseLogs(target);
  press(target, 'Continue');
  const signal = prepare.mock.calls[0]?.[2];
  expect(signal?.aborted).toBe(false);
  visit(target, 'Harness');
  select(target, 'codex');
  expect(signal?.aborted).toBe(true);
  resolvePackage(new Blob(['obsolete package']));
  await pending;
  visit(target, 'Review and install');
  expect(target.textContent).not.toContain('Download installer');
  expect(requiredElement(target, 'code').textContent).toContain('/codex/install.sh');
  visit(target, 'Harness');
  select(target, 'claude-code');
  visit(target, 'Telemetry');
  expect(requiredElement<HTMLInputElement>(target, 'input[value="skip"]').checked).toBe(true);
  visit(target, 'Review and install');
  expect(prepare).toHaveBeenCalledTimes(1);
});
