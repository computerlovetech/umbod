import { flushSync, mount, unmount } from 'svelte';
import { expect, test, vi } from 'vitest';
import { InMemoryPersonalConnectionsApi } from '#lib/personal-connections/infrastructure/in-memory-api.js';
import { InMemoryAttemptScheduler } from '#lib/personal-connections/infrastructure/in-memory-attempt-scheduler.js';
import { ConnectionState } from '#lib/personal-connections/state/connection-state.svelte.js';
import { authorizationHealth, selection } from '#lib/personal-connections/test-fixtures.js';
import ConnectionCard from './ConnectionCard.svelte';

test.each([false, true])('keeps connection details mounted while closed (embedded: %s)', async (embedded): Promise<void> => {
  const api = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
  const state = new ConnectionState(selection, api, vi.fn(), undefined, undefined, new InMemoryAttemptScheduler());
  const target = document.createElement('div');
  document.body.append(target);
  const component = mount(ConnectionCard, { target, props: { state, embedded } });
  try {
    const trigger = Array.from(target.querySelectorAll('button')).find((button) => button.textContent?.trim() === 'Connection details');
    if (!trigger) throw new Error('Connection details disclosure is missing');
    const panel = document.getElementById(trigger.getAttribute('aria-controls') ?? '');
    if (!panel) throw new Error('Connection details panel is missing');
    const details = panel.querySelector('dl');
    expect(details?.textContent).toContain('Authorization saved');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(panel.hidden).toBe(true);
    trigger.click(); flushSync();
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    expect(panel.hidden).toBe(false);
    trigger.click(); flushSync();
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(panel.hidden).toBe(true);
    expect(panel.querySelector('dl')).toBe(details);
  } finally {
    await unmount(component);
    target.remove();
    state.dispose();
  }
});
