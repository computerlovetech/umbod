import { describe, expect, test, vi } from 'vitest';
import { OpenApiConnectorReloadState } from './openapi-connector-reload-state.svelte';

function deferred(): { promise: Promise<void>; resolve: () => void; reject: (reason: unknown) => void } {
  let resolve!: () => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<void>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe('OpenApiConnectorReloadState', () => {
  test('exposes pending state while reloading and clears it after success', async () => {
    const pending = deferred();
    const reload = vi.fn(() => pending.promise);
    const state = new OpenApiConnectorReloadState(reload);

    const result = state.retry();
    expect(state.retrying).toBe(true);
    pending.resolve();
    await result;

    expect(state.retrying).toBe(false);
    expect(reload).toHaveBeenCalledOnce();
  });

  test('clears pending state after failure', async () => {
    const state = new OpenApiConnectorReloadState(async () => {
      throw new Error('failed');
    });

    await expect(state.retry()).rejects.toThrow('failed');
    expect(state.retrying).toBe(false);
  });
});
