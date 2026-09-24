import { describe, expect, it, vi } from 'vitest';
import { BrowserRequestError } from '$lib/admin/infrastructure/browser-request';
import { MountedDetailProxy } from './mounted-detail-proxy.svelte';

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void; reject: (error: Error) => void };
function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((accept, decline) => { resolve = accept; reject = decline; });
  return { promise, resolve, reject };
}
async function flush(): Promise<void> { await Promise.resolve(); await Promise.resolve(); }

describe('MountedDetailProxy', (): void => {
  it('seeds SSR detail and reuses its cache without loading', (): void => {
    const loader = vi.fn(async (): Promise<string> => 'loaded');
    const proxy = new MountedDetailProxy({ selectedId: 'a', initialDetail: 'seed', loadDetail: loader });
    proxy.select('a');
    expect(proxy.mounted).toBe('seed');
    expect(loader).not.toHaveBeenCalled();
  });

  it.each(['constructor', '__proto__', 'toString'])('caches prototype-like ID %s safely', (id): void => {
    const proxy = new MountedDetailProxy({ selectedId: id, initialDetail: `${id}-detail` });
    expect(proxy.read(id)).toBe(`${id}-detail`);
    proxy.select(id);
    expect(proxy.mounted).toBe(`${id}-detail`);
  });

  it('retries a failed selected detail', async (): Promise<void> => {
    const loader = vi.fn().mockRejectedValueOnce(new BrowserRequestError(undefined, new Error('failed'))).mockResolvedValueOnce('ready');
    const proxy = new MountedDetailProxy<string>({ selectedId: 'a', loadDetail: loader });
    proxy.retry(); await flush();
    expect(proxy.failed).toBe(true);
    proxy.retry(); await flush();
    expect(proxy.mounted).toBe('ready');
  });

  it('caches stale cross-selection success even when abort is ignored', async (): Promise<void> => {
    const a = deferred<string>();
    const loader = vi.fn((id: string): Promise<string> => id === 'a' ? a.promise : Promise.resolve('b'));
    const proxy = new MountedDetailProxy<string>({ loadDetail: loader });
    proxy.select('a'); proxy.select('b'); await flush(); a.resolve('a'); await flush();
    proxy.select('a');
    expect(proxy.mounted).toBe('a');
    expect(loader).toHaveBeenCalledTimes(2);
  });

  it('synchronizes authoritative server data and invalidates an older request', async (): Promise<void> => {
    const older = deferred<string>();
    const loader = vi.fn((): Promise<string> => older.promise);
    const proxy = new MountedDetailProxy<string>({ selectedId: 'a', loadDetail: loader });
    proxy.retry();
    proxy.synchronize('a', 'server');
    older.resolve('stale');
    await flush();
    expect(proxy.mounted).toBe('server');
    expect(proxy.read('a')).toBe('server');
    expect(proxy.loading).toBe(false);
    expect(proxy.failed).toBe(false);
  });

  it('prevents an older same-ID request from overwriting a retry', async (): Promise<void> => {
    const first = deferred<string>(); const second = deferred<string>();
    const loader = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const proxy = new MountedDetailProxy<string>({ selectedId: 'a', loadDetail: loader });
    proxy.retry(); proxy.retry(); second.resolve('new'); await flush(); first.resolve('old'); await flush();
    expect(proxy.mounted).toBe('new');
    expect(proxy.read('a')).toBe('new');
  });
});
