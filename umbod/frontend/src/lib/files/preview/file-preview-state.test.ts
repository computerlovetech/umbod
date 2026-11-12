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
      const state = new FilePreviewState(source, registry);
      await state.select(markdownFile);
      expect(state.phase).toBe(phase);
      expect(state.content).toBe(content);
      expect(state.adapter).toBe(markdownPreviewAdapter);
      state.dispose();
    }
  });

  test('never reads directories, undiscoverable, unreadable or unsupported files', async (): Promise<void> => {
    const source = new InMemoryFileContent(async (): Promise<string> => 'secret');
    const state = new FilePreviewState(source, registry);
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
    const state = new FilePreviewState(new InMemoryFileContent(async (): Promise<string> => { throw error; }), registry);
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
    const state = new FilePreviewState(source, registry);
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
    const state = new FilePreviewState(source, registry);
    const pending = state.select(markdownFile);
    await state.select({ ...markdownFile, permissions: { ...markdownFile.permissions, can_read: false } });
    expect(source.requests[0].signal.aborted).toBe(true);
    obsolete.resolve('secret');
    await pending;
    expect(state.phase).toBe('hidden');
    expect(state.content).toBe('');
    const later = deferred<string>();
    const disposedSource = new InMemoryFileContent(async (): Promise<string> => later.promise);
    const disposed = new FilePreviewState(disposedSource, registry);
    const loading = disposed.select(markdownFile);
    disposed.dispose();
    later.reject(new Error('obsolete'));
    await loading;
    await disposed.select(markdownFile);
    expect(disposed.phase).toBe('hidden');
    expect(disposedSource.requests).toHaveLength(1);
    state.dispose();
  });

  test('file navigation composes preview loading and clears content on folder navigation', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture.map((node) => node.id === fileId ? markdownFile : node));
    const source = new InMemoryFileContent(async (): Promise<string> => '# Preview');
    const preview = new FilePreviewState(source, registry);
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
