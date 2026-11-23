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
  await wizard.prepareAndCopy();
  expect(source.requests).toEqual([]);
  wizard.goTo('review');

  try {
    await wizard.prepareAndCopy();
    expect(wizard.claim).toMatchObject({ status: 'ready', command: clipboard.text });
    expect(clipboard.text).toContain(source.code);
    await vi.advanceTimersByTimeAsync(600_000);
    expect(wizard.claim).toEqual({ status: 'expired' });
    clipboard.text = '';
    await wizard.copyPreparedCommand();
    expect(clipboard.text).toBe('');
    expect(source.requests).toHaveLength(1);

    source.code = 'B'.repeat(43);
    await wizard.prepareAndCopy();
    expect(wizard.claim).toMatchObject({ status: 'ready', command: clipboard.text });
    expect(clipboard.text).toContain(source.code);
    expect(source.requests).toHaveLength(2);
  } finally {
    wizard.clearClaim();
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
  const preparing = wizard.prepareAndCopy();
  available = false;
  response.resolve();
  await preparing;
  expect(wizard.includesLogs).toBe(false);
  expect(wizard.claim).toEqual({ status: 'idle' });
  expect(clipboard.text).toBe('');
  wizard.clearClaim();
});
