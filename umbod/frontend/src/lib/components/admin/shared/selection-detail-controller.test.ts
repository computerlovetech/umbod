import { describe, expect, test, vi } from 'vitest';
import { BrowserRequestError } from '$lib/admin/infrastructure/browser-request';
import { SelectionDetailController } from './selection-detail-controller.svelte';
import { InMemorySelectionUrlAdapter } from './selection-url-port';

type Item = { id: string };

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void; reject: (reason: unknown) => void } {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function controller(options: { items?: Item[]; selectedId?: string; loader?: (id: string, signal?: AbortSignal) => Promise<string>; url?: InMemorySelectionUrlAdapter; hook?: (id: string) => void } = {}): SelectionDetailController<Item, string> {
  return new SelectionDetailController({
    items: options.items ?? [{ id: 'a' }, { id: 'b' }],
    itemId: (item) => item.id,
    selectedId: options.selectedId,
    loadDetail: options.loader,
    url: options.url ?? new InMemorySelectionUrlAdapter(),
    onSelectionChange: options.hook
  });
}

describe('SelectionDetailController through SelectionUrlPort', () => {
  test('reads initial selection without replacing URL and replaces it on explicit selection', () => {
    const url = new InMemorySelectionUrlAdapter('b');
    const state = controller({ url });
    expect(state.selectedId).toBe('b');
    expect(url.replacements).toEqual([]);
    state.select('a');
    expect(state.selectedItem?.id).toBe('a');
    expect(url.replacements).toEqual(['a']);
  });

  test('falls back for invalid selection and supports empty items without canonicalizing URL', () => {
    const url = new InMemorySelectionUrlAdapter('missing');
    expect(controller({ url }).selectedId).toBe('a');
    expect(controller({ items: [], url }).selectedItem).toBeNull();
    expect(url.replacements).toEqual([]);
  });

  test('reuses cached detail', async () => {
    const loader = vi.fn(async (id: string) => `${id}-detail`);
    const state = controller({ loader });
    state.select('b');
    await vi.waitFor(() => expect(state.detail).toBe('b-detail'));
    state.select('a');
    await vi.waitFor(() => expect(state.detail).toBe('a-detail'));
    state.select('b');
    expect(loader.mock.calls.filter(([id]) => id === 'b')).toHaveLength(1);
  });

  test('clears mounted detail while a different connector loads', () => {
    const pending = deferred<string>();
    const state = new SelectionDetailController<Item, string>({
      items: [{ id: 'a' }, { id: 'b' }],
      itemId: (item) => item.id,
      selectedId: 'a',
      initialDetail: 'detail-a',
      loadDetail: () => pending.promise,
      url: new InMemorySelectionUrlAdapter()
    });
    state.select('b');
    expect(state.detail).toBeNull();
    expect(state.loading).toBe(true);
  });

  test('does not display stale results and cancels the stale request', async () => {
    const first = deferred<string>();
    const second = deferred<string>();
    const signals: AbortSignal[] = [];
    const state = controller({ loader: (id, signal) => {
      if (signal) signals.push(signal);
      return id === 'a' ? first.promise : second.promise;
    } });
    state.select('b');
    state.select('a');
    expect(signals[0]?.aborted).toBe(true);
    second.resolve('stale-b');
    await Promise.resolve();
    expect(state.detail).not.toBe('stale-b');
    first.resolve('fresh-a');
    await vi.waitFor(() => expect(state.detail).toBe('fresh-a'));
  });

  test('exposes failure and retries', async () => {
    const loader = vi.fn().mockRejectedValueOnce(new BrowserRequestError(undefined, new Error('failed'))).mockResolvedValueOnce('detail-b');
    const state = controller({ loader });
    state.select('b');
    await vi.waitFor(() => expect(state.failed).toBe(true));
    state.retry();
    await vi.waitFor(() => expect(state.detail).toBe('detail-b'));
    expect(state.failed).toBe(false);
  });

  test('is idempotent for current ID, rejects unknown IDs, and invokes reset hook once', () => {
    const hook = vi.fn();
    const url = new InMemorySelectionUrlAdapter();
    const state = controller({ selectedId: 'a', url, hook });
    state.select('a');
    state.select('missing');
    expect(hook).not.toHaveBeenCalled();
    state.select('b');
    expect(hook).toHaveBeenCalledOnce();
    expect(hook).toHaveBeenCalledWith('b');
    expect(url.replacements).toEqual(['b']);
  });
});
