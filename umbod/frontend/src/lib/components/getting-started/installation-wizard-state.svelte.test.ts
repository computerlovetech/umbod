import { afterEach, expect, test, vi } from 'vitest';
import { InMemoryClipboardWriter } from '#lib/admin/clipboard.js';
import { InMemoryTelemetryInstallClaims } from '#lib/telemetry-setup/in-memory-api.test-support.js';
import { InstallationWizardState } from './installation-wizard-state.svelte';

afterEach((): void => { vi.useRealTimers(); });

test('removes the expired command and only requests a replacement after an explicit action', async (): Promise<void> => {
  vi.useFakeTimers();
  const source = new InMemoryTelemetryInstallClaims();
  const clipboard = new InMemoryClipboardWriter();
  const wizard = new InstallationWizardState(() => 'https://site.test/api/install/v1', () => source, clipboard);
  wizard.selectTelemetry('logs');
  await wizard.copyCommand();
  expect(source.requests).toEqual([]);
  wizard.goTo('review');

  try {
    await wizard.copyCommand();
    expect(clipboard.text).toContain(source.code);
    wizard.toggleCommandVisibility();
    expect(wizard.commandPreview).toBe(clipboard.text);
    await vi.advanceTimersByTimeAsync(600_000);
    expect(wizard.copyLabel).toBe('Generate new command');
    expect(wizard.canRevealCommand).toBe(false);
    expect(wizard.commandPreview).not.toContain(source.code);
    expect(source.requests).toHaveLength(1);

    source.code = 'B'.repeat(43);
    await wizard.copyCommand();
    expect(clipboard.text).toContain(source.code);
    expect(wizard.commandPreview).not.toContain(source.code);
    expect(source.requests).toHaveLength(2);
  } finally {
    wizard.resetCommand();
  }
});

test('does not publish or copy a response after telemetry eligibility is removed', async (): Promise<void> => {
  const response = Promise.withResolvers<void>();
  const source = new InMemoryTelemetryInstallClaims();
  source.beforeCreate = () => response.promise;
  const clipboard = new InMemoryClipboardWriter();
  let available = true;
  const wizard = new InstallationWizardState(() => 'https://site.test/api/install/v1', () => available ? source : undefined, clipboard);
  wizard.selectTelemetry('logs');
  wizard.goTo('review');
  try {
    const preparing = wizard.copyCommand();
    available = false;
    response.resolve();
    await preparing;
    expect(wizard.includesLogs).toBe(false);
    expect(wizard.canRevealCommand).toBe(false);
    expect(wizard.commandPreview).not.toContain(source.code);
    expect(clipboard.text).toBe('');
    wizard.discardObsoleteCommand();
    expect(source.requests[0]?.signal.aborted).toBe(true);
    available = true;
    expect(wizard.canRevealCommand).toBe(false);
    expect(wizard.copyLabel).toBe('Copy command');
  } finally {
    wizard.resetCommand();
  }
});
