import { describe, expect, test } from 'vitest';
import type { CodexPluginArchive } from '$lib/codex-plugin/contracts';
import { InMemoryCodexPluginDownloader, InMemoryCodexPluginPackager, testArchive } from '$lib/codex-plugin/in-memory.test-support';
import { CodexPluginState } from './codex-plugin-state.svelte';

function deferredArchive(): { promise: Promise<CodexPluginArchive>; resolve: (value: CodexPluginArchive) => void } {
  let resolve!: (value: CodexPluginArchive) => void;
  const promise = new Promise<CodexPluginArchive>((settle): void => { resolve = settle; });
  return { promise, resolve };
}

describe('Codex plugin download', (): void => {
  test('downloads the current endpoint and registers the marketplace from the extracted folder', async (): Promise<void> => {
    const packager = new InMemoryCodexPluginPackager();
    const downloader = new InMemoryCodexPluginDownloader();
    const state = new CodexPluginState(() => 'https://umbod.test/team/mcp', packager, downloader);
    expect(state.installation).toBeNull();
    await state.download();
    expect(packager.requests).toEqual([{ endpoint: 'https://umbod.test/team/mcp' }]);
    expect(downloader.downloads).toHaveLength(1);
    expect(state.installation?.command).toBe('codex plugin marketplace add .');
    expect(state.pending).toBe(false);
  });

  test('blocks duplicate clicks while preparing the archive', async (): Promise<void> => {
    const response = deferredArchive();
    const packager = new InMemoryCodexPluginPackager();
    packager.result = response.promise;
    const downloader = new InMemoryCodexPluginDownloader();
    const state = new CodexPluginState(() => 'https://umbod.test/mcp', packager, downloader);
    const download = state.download();
    expect(state.pending).toBe(true);
    await state.download();
    expect(packager.requests).toHaveLength(1);
    response.resolve(testArchive('https://umbod.test/mcp'));
    await download;
    expect(downloader.downloads).toHaveLength(1);
  });

  test('does not save an obsolete archive or expose stale commands after the endpoint changes', async (): Promise<void> => {
    let endpoint = 'https://one.test/mcp';
    const response = deferredArchive();
    const packager = new InMemoryCodexPluginPackager();
    packager.result = response.promise;
    const downloader = new InMemoryCodexPluginDownloader();
    const state = new CodexPluginState(() => endpoint, packager, downloader);
    const download = state.download();
    endpoint = 'https://two.test/mcp';
    response.resolve(testArchive('https://one.test/mcp'));
    await download;
    expect(downloader.downloads).toEqual([]);
    expect(state.installation).toBeNull();
    expect(state.pending).toBe(false);
    packager.result = null;
    await state.download();
    expect(downloader.downloads[0].endpoint).toBe(endpoint);
    endpoint = 'https://three.test/mcp';
    expect(state.installation).toBeNull();
  });

  test('does not download after the owning component is disposed', async (): Promise<void> => {
    const response = deferredArchive();
    const packager = new InMemoryCodexPluginPackager();
    packager.result = response.promise;
    const downloader = new InMemoryCodexPluginDownloader();
    const state = new CodexPluginState(() => 'https://umbod.test/mcp', packager, downloader);
    const download = state.download();
    state.dispose();
    response.resolve(testArchive('https://umbod.test/mcp'));
    await download;
    await state.download();
    expect(downloader.downloads).toEqual([]);
    expect(packager.requests).toHaveLength(1);
  });

  test('rejects secret-bearing endpoints before invoking external adapters', async (): Promise<void> => {
    const packager = new InMemoryCodexPluginPackager();
    const downloader = new InMemoryCodexPluginDownloader();
    const state = new CodexPluginState(() => 'https://umbod.test/mcp?token=secret', packager, downloader);
    await state.download();
    expect(packager.requests).toEqual([]);
    expect(downloader.downloads).toEqual([]);
    expect(state.error).not.toContain('token=secret');
    expect(state.error).toContain('Could not download');
    expect(state.pending).toBe(false);
  });

  test.each(['packager', 'downloader'] as const)('recovers from %s failures without exposing the exception', async (failing): Promise<void> => {
    const packager = new InMemoryCodexPluginPackager();
    const downloader = new InMemoryCodexPluginDownloader();
    const adapter = failing === 'packager' ? packager : downloader;
    adapter.failure = new Error('private diagnostic');
    const state = new CodexPluginState(() => 'https://umbod.test/mcp', packager, downloader);
    await state.download();
    expect(state.error).toContain('Could not download');
    expect(state.error).not.toContain('private diagnostic');
    expect(state.installation).toBeNull();
    adapter.failure = null;
    await state.download();
    expect(state.error).toBe('');
    expect(state.installation).not.toBeNull();
    expect(downloader.downloads).toHaveLength(1);
  });

  test('rejects an archive generated for another endpoint', async (): Promise<void> => {
    const packager = new InMemoryCodexPluginPackager();
    packager.result = Promise.resolve(testArchive('https://other.test/mcp'));
    const downloader = new InMemoryCodexPluginDownloader();
    const state = new CodexPluginState(() => 'https://umbod.test/mcp', packager, downloader);
    await state.download();
    expect(downloader.downloads).toEqual([]);
    expect(state.error).not.toBe('');
  });
});
