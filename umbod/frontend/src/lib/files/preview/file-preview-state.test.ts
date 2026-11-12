import { InMemoryPreviewConfiguration } from '$lib/files/preview/in-memory-configuration.test-support';
import { describe, expect, test, vi } from 'vitest';
import { deferred, fileId, filesystemFixture, filesystemNode, folderId, rootId } from '../fixtures.test-support';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api.test-support';
import { FilesState } from '../state/files-state.svelte';
import { markdownPreviewAdapter } from '$lib/components/files/preview/markdown-adapter';
import { PreviewReadError, PreviewRegistry } from './ports';
import { FilePreviewState } from './file-preview-state.svelte';
import { InMemoryFileContent } from './in-memory-content.test-support';

const markdownFile = filesystemNode({ id: fileId, parent_id: folderId, name: 'README.md', kind: 'file' });
const registry = new PreviewRegistry([markdownPreviewAdapter]);

describe('file previews', (): void => {
  test('loads supported content and distinguishes empty content', async (): Promise<void> => {
    for (const [content, phase] of [['# Notes', 'ready'], ['', 'empty'], [' \n', 'empty']]) {
      const source = new InMemoryFileContent(async (): Promise<string> => content);
      const state = new FilePreviewState(source, registry, new InMemoryPreviewConfiguration(257));
      await state.select(markdownFile);
      expect(state.phase).toBe(phase);
      expect(state.content).toBe(content);
      expect(state.adapter).toBe(markdownPreviewAdapter);
      state.dispose();
    }
  });

  test('never reads directories, undiscoverable, unreadable or unsupported files', async (): Promise<void> => {
    const source = new InMemoryFileContent(async (): Promise<string> => 'secret');
    const state = new FilePreviewState(source, registry, new InMemoryPreviewConfiguration(257));
    const permissions = markdownFile.permissions;
    for (const node of [
      { ...markdownFile, kind: 'directory' as const },
      { ...markdownFile, permissions: { ...permissions, can_read: false } },
      { ...markdownFile, permissions: { ...permissions, can_discover: false } }
    ]) {
      await state.select(node);
      expect(state.phase).toBe('hidden');
    }
    await state.select({ ...markdownFile, name: 'photo.png' });
    expect(state.phase).toBe('unsupported');
    expect(source.requests).toHaveLength(0);
    state.dispose();
  });

  test.each([
    [new PreviewReadError('sign-in'), 'sign-in'],
    [new PreviewReadError('denied'), 'denied'],
    [new PreviewReadError('missing'), 'missing'],
    [new PreviewReadError('too-large'), 'too-large'],
    [new Error('private diagnostic'), 'error']
  ])('classifies read failures without retaining content', async (error: Error, phase: string): Promise<void> => {
    const state = new FilePreviewState(new InMemoryFileContent(async (): Promise<string> => { throw error; }), registry, new InMemoryPreviewConfiguration(257));
    await state.select(markdownFile);
    expect(state.phase).toBe(phase);
    expect(state.content).toBe('');
    state.dispose();
  });

  test('loading is observable, retry recovers, and duplicate pending retries are ignored', async (): Promise<void> => {
    const result = deferred<string>();
    let attempts = 0;
    const source = new InMemoryFileContent(async (): Promise<string> => {
      if (++attempts === 1) throw new Error('offline');
      return result.promise;
    });
    const state = new FilePreviewState(source, registry, new InMemoryPreviewConfiguration(257));
    await state.select(markdownFile);
    const retry = state.retry();
    expect(state.phase).toBe('loading');
    await state.retry();
    expect(source.requests).toHaveLength(2);
    result.resolve('# Recovered');
    await retry;
    expect(state.phase).toBe('ready');
    expect(state.content).toBe('# Recovered');
    state.dispose();
  });

  test('navigation, access loss and disposal abort and fence obsolete reads', async (): Promise<void> => {
    const obsolete = deferred<string>();
    const source = new InMemoryFileContent(async (): Promise<string> => obsolete.promise);
    const state = new FilePreviewState(source, registry, new InMemoryPreviewConfiguration(257));
    const pending = state.select(markdownFile);
    await vi.waitFor((): void => expect(source.requests).toHaveLength(1));
    await state.select({ ...markdownFile, permissions: { ...markdownFile.permissions, can_read: false } });
    expect(source.requests[0].signal.aborted).toBe(true);
    obsolete.resolve('secret');
    await pending;
    expect(state.phase).toBe('hidden');
    expect(state.content).toBe('');
    const later = deferred<string>();
    const disposedSource = new InMemoryFileContent(async (): Promise<string> => later.promise);
    const disposed = new FilePreviewState(disposedSource, registry, new InMemoryPreviewConfiguration(257));
    const loading = disposed.select(markdownFile);
    await vi.waitFor((): void => expect(disposedSource.requests).toHaveLength(1));
    disposed.dispose();
    later.reject(new Error('obsolete'));
    await loading;
    await disposed.select(markdownFile);
    expect(disposed.phase).toBe('hidden');
    expect(disposedSource.requests).toHaveLength(1);
    state.dispose();
  });

  test('render failures clear content and retry recovers while obsolete handlers cannot change newer selections', async (): Promise<void> => {
    const state = new FilePreviewState(new InMemoryFileContent(async (): Promise<string> => '# Preview'), registry, new InMemoryPreviewConfiguration(257));
    try {
      await state.select(markdownFile);
      const obsoleteError = state.createRenderErrorHandler();
      await state.select(markdownFile);
      obsoleteError();
      expect(state.phase).toBe('ready');
      state.createRenderErrorHandler()();
      expect(state.phase).toBe('error');
      expect(state.content).toBe('');
      await state.retry();
      expect(state.phase).toBe('ready');
      const resetError = state.createRenderErrorHandler();
      state.reset();
      resetError();
      expect(state.phase).toBe('hidden');
      await state.select(markdownFile);
      const disposedError = state.createRenderErrorHandler();
      state.dispose();
      disposedError();
      expect(state.phase).toBe('hidden');
    } finally {
      state.dispose();
    }
  });

  test('file navigation composes preview loading and clears content on folder navigation', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture.map((node) => node.id === fileId ? markdownFile : node));
    const source = new InMemoryFileContent(async (): Promise<string> => '# Preview');
    const preview = new FilePreviewState(source, registry, new InMemoryPreviewConfiguration(257));
    const files = new FilesState(api, undefined, preview);
    try {
      await files.load(fileId);
      await vi.waitFor((): void => expect(preview.phase).toBe('ready'));
      await files.load(folderId);
      expect(preview.phase).toBe('hidden');
      expect(preview.content).toBe('');
    } finally {
      files.dispose();
    }
  });
});

test.each(['reset', 'dispose', 'access-loss', 'unsupported'] as const)('fences preview reads cancelled during configuration: %s', async (action: 'reset' | 'dispose' | 'access-loss' | 'unsupported'): Promise<void> => {
  const configuration = deferred<{ filesystemPreviewMaxBytes: number }>();
  const source = new InMemoryFileContent(async (): Promise<string> => '# Obsolete');
  const state = new FilePreviewState(source, registry, { get: (): Promise<{ filesystemPreviewMaxBytes: number }> => configuration.promise });
  try {
    const pending = state.select(markdownFile);
    expect(state.phase).toBe('loading');
    expect(source.requests).toHaveLength(0);
    if (action === 'reset') state.reset();
    if (action === 'dispose') state.dispose();
    if (action === 'access-loss') await state.select({ ...markdownFile, permissions: { ...markdownFile.permissions, can_read: false } });
    if (action === 'unsupported') await state.select({ ...markdownFile, name: 'archive.zip' });
    configuration.resolve({ filesystemPreviewMaxBytes: 511 });
    await pending;
    expect(source.requests).toHaveLength(0);
    expect(state.maxBytes).toBeUndefined();
    expect(state.phase).toBe(action === 'unsupported' ? 'unsupported' : 'hidden');
  } finally {
    state.dispose();
  }
});

test('new selection wins when configuration resolves out of order', async (): Promise<void> => {
  const obsolete = deferred<{ filesystemPreviewMaxBytes: number }>();
  let calls = 0;
  const source = new InMemoryFileContent(async (): Promise<string> => '# Current');
  const state = new FilePreviewState(source, registry, { get: async (): Promise<{ filesystemPreviewMaxBytes: number }> => ++calls === 1 ? obsolete.promise : { filesystemPreviewMaxBytes: 511 } });
  try {
    const pending = state.select(markdownFile);
    await state.select({ ...markdownFile, id: rootId });
    obsolete.resolve({ filesystemPreviewMaxBytes: 1 });
    await pending;
    expect(source.requests).toHaveLength(1);
    expect(source.requests[0].id).toBe(rootId);
    expect(state.maxBytes).toBe(511);
    expect(state.phase).toBe('ready');
  } finally {
    state.dispose();
  }
});

test('configuration failures do not read content and can be retried', async (): Promise<void> => {
  let attempts = 0;
  const source = new InMemoryFileContent(async (): Promise<string> => '# Current');
  const state = new FilePreviewState(source, registry, { get: async (): Promise<{ filesystemPreviewMaxBytes: number }> => {
    if (++attempts === 1) throw new Error('private config detail');
    return { filesystemPreviewMaxBytes: 511 };
  } });
  try {
    await state.select(markdownFile);
    expect(state.phase).toBe('error');
    expect(source.requests).toHaveLength(0);
    await state.retry();
    expect(state.phase).toBe('ready');
    expect(state.maxBytes).toBe(511);
  } finally {
    state.dispose();
  }
});

test.each([[1, '1 byte'], [1024, '1 KiB'], [1048576, '1 MiB'], [1048577, '1048577 bytes'], [Number.MAX_SAFE_INTEGER, '9007199254740991 bytes']])('formats the resolved maximum exactly: %s', async (bytes: number | string, expected: number | string): Promise<void> => {
  const state = new FilePreviewState(new InMemoryFileContent(async (): Promise<string> => '# Current'), registry, new InMemoryPreviewConfiguration(Number(bytes)));
  try {
    await state.select(markdownFile);
    expect(state.formattedMaxSize).toBe(expected);
  } finally {
    state.dispose();
  }
});
