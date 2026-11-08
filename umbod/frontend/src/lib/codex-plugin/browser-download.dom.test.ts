import { afterEach, expect, test, vi } from 'vitest';
import { BrowserCodexPluginDownloader } from './browser-package';
import { testArchive } from './in-memory.test-support';

afterEach((): void => {
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

test('saves a ZIP with the expected filename and releases the temporary anchor and Blob URL', (): void => {
  vi.useFakeTimers();
  const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:umbod-test');
  const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation((): void => {});
  let observed: { attached: boolean; filename: string; href: string } | null = null;
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement): void {
    observed = { attached: this.isConnected, filename: this.download, href: this.href };
  });
  new BrowserCodexPluginDownloader().save(testArchive('https://umbod.test/mcp'));
  expect(observed).toEqual({ attached: true, filename: 'umbod-codex-0123456789ab.zip', href: 'blob:umbod-test' });
  expect(create).toHaveBeenCalledWith(expect.objectContaining({ type: 'application/zip' }));
  expect(document.querySelector('a[download]')).toBeNull();
  expect(revoke).not.toHaveBeenCalled();
  vi.runAllTimers();
  expect(revoke).toHaveBeenCalledWith('blob:umbod-test');
});

test('cleans up browser resources when dispatching the download fails', (): void => {
  vi.useFakeTimers();
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:umbod-test');
  const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation((): void => {});
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation((): never => { throw new Error('Download blocked'); });
  expect((): void => new BrowserCodexPluginDownloader().save(testArchive('https://umbod.test/mcp'))).toThrow('Download blocked');
  expect(document.querySelector('a[download]')).toBeNull();
  vi.runAllTimers();
  expect(revoke).toHaveBeenCalledWith('blob:umbod-test');
});
