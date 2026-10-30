import { expect, it, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import { IdentityDirectoryApi } from '$lib/identity-directory/api';
import { browserTransport } from '$lib/admin/infrastructure/transport';
import IdentityObservation from './IdentityObservation.svelte';

it.each([401, 403])('keeps observation HTTP %s failures background-safe and retries without navigation', async (status: number): Promise<void> => {
  const assign = vi.spyOn(window.location, 'assign');
  const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status }));
  const api = new IdentityDirectoryApi(browserTransport({
    fetch: request,
    configuration: { get: async () => ({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' }) }
  }));
  const target = document.createElement('div');
  document.body.append(target);
  const component = mount(IdentityObservation, { target, props: {
    observation: api.observations,
    environment: { now: (): number => 0, visible: (): boolean => true, every: (): (() => void) => (): void => {} }
  } });
  flushSync();
  await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(1));
  await new Promise<void>((resolve) => queueMicrotask(resolve));
  window.dispatchEvent(new Event('focus'));
  await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(2));
  expect(assign).not.toHaveBeenCalled();
  expect(target.textContent).toBe('');
  expect(document.querySelector('[role="alert"]')).toBeNull();
  await unmount(component);
  target.remove();
  assign.mockRestore();
});

it('wires browser resume events independently and tears them down on unmount', async (): Promise<void> => {
  let now = 0;
  let visible = true;
  const observe = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
  const stop = vi.fn();
  const target = document.createElement('div');
  document.body.append(target);
  const component = mount(IdentityObservation, { target, props: {
    observation: { observe },
    environment: { now: (): number => now, visible: (): boolean => visible, every: (): (() => void) => stop }
  } });
  flushSync();
  expect(observe).toHaveBeenCalledTimes(1);
  await Promise.resolve();
  now = 60_000;
  visible = false;
  document.dispatchEvent(new Event('visibilitychange'));
  expect(observe).toHaveBeenCalledTimes(1);
  visible = true;
  document.dispatchEvent(new Event('visibilitychange'));
  await Promise.resolve();
  expect(observe).toHaveBeenCalledTimes(2);
  now = 120_000;
  window.dispatchEvent(new Event('focus'));
  expect(observe).toHaveBeenCalledTimes(3);
  await unmount(component);
  now = 180_000;
  window.dispatchEvent(new Event('focus'));
  document.dispatchEvent(new Event('visibilitychange'));
  expect(observe).toHaveBeenCalledTimes(3);
  expect(stop).toHaveBeenCalledTimes(1);
  target.remove();
});
