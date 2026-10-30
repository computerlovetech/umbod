import { Window } from 'happy-dom';
import { render } from 'svelte/server';
import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';
import { deferred, filesystemFixture, folderId, rootId } from '$lib/files/fixtures.test-support';
import { InMemoryFilesApi } from '$lib/files/infrastructure/in-memory-api.test-support';
import { FilesNavigationState } from '$lib/files/state/navigation-state.svelte';
import { FilesState } from '$lib/files/state/files-state.svelte';
import type { Breadcrumbs, NodeSummary } from '$lib/files/domain/schemas';
import FilesNavigation from './FilesNavigation.svelte';

function documentFor(state: FilesNavigationState): Window['document'] {
  const window = new Window();
  window.document.body.innerHTML = render(FilesNavigation, { props: { state, signIn: vi.fn() } }).body;
  return window.document;
}

function fixture(canRead: (node: NodeSummary) => boolean = () => true): { api: InMemoryFilesApi; state: FilesNavigationState } {
  const api = new InMemoryFilesApi(rootId, filesystemFixture, undefined, undefined, canRead);
  return { api, state: new FilesNavigationState(api.filesystem) };
}

describe('compact file navigation', () => {
  test('complete root has no redundant path bar or Up button', async (): Promise<void> => {
    const { state } = fixture();
    await state.select(filesystemFixture[0]);
    const document = documentFor(state);
    expect(document.querySelector('nav')).toBeNull();
    expect(document.querySelector('a, button')).toBeNull();
  });

  test('ancestors are native links, the current item is plain and separators are hidden', async (): Promise<void> => {
    const { state } = fixture();
    await state.select(filesystemFixture[2]);
    const document = documentFor(state);
    expect(Array.from(document.querySelectorAll('.desktop-path a')).map((link) => link.getAttribute('href'))).toEqual(['/files', '/files?node=' + folderId]);
    const current = document.querySelector('[aria-current="page"]');
    expect(current?.tagName).toBe('SPAN');
    expect(current?.textContent).toBe('Notes.txt');
    expect(current?.getAttribute('title')).toBe('Notes.txt');
    expect(document.querySelectorAll('.desktop-path [aria-hidden="true"]')).toHaveLength(2);
    expect(document.querySelector('button')).toBeNull();
    expect(document.body.textContent).not.toContain('Up');
    expect(document.querySelector('.mobile-path a')?.getAttribute('href')).toBe('/files?node=' + folderId);
    expect(document.querySelector('.mobile-path .name')?.textContent).toBe('Projects');
  });

  test('mobile parent is the confirmed root for a first-level folder', async (): Promise<void> => {
    const { state } = fixture();
    await state.select(filesystemFixture[1]);
    const link = documentFor(state).querySelector('.mobile-path a');
    expect(link?.getAttribute('href')).toBe('/files');
    expect(link?.textContent).toBe('‹Files');
  });

  test('partial paths disclose unavailable ancestors without names, ids or fabricated links', async (): Promise<void> => {
    const { state } = fixture((node) => node.id !== folderId);
    await state.select(filesystemFixture[2]);
    const document = documentFor(state);
    expect(document.body.textContent).not.toContain('Projects');
    expect(document.body.innerHTML).not.toContain(rootId);
    expect(document.body.innerHTML).not.toContain(folderId);
    expect(document.querySelector('a, button')).toBeNull();
    expect(document.querySelector('.partial')?.textContent).toContain('Earlier folders unavailable');
    expect(document.querySelector('.mobile-path')?.textContent).toContain('Earlier folders unavailable');
  });

  test('partial visible parent remains a native mobile link without a fake root', async (): Promise<void> => {
    const { state } = fixture((node) => node.id !== rootId);
    await state.select(filesystemFixture[2]);
    const document = documentFor(state);
    expect(document.querySelector('.mobile-path a')?.getAttribute('href')).toBe('/files?node=' + folderId);
    expect(document.querySelector('a[href="/files"]')).toBeNull();
    expect(document.querySelector('[aria-haspopup="menu"]')).toBeNull();
  });

  test.each([4, 5, 8])('long paths of %s items offer only omitted known ancestors in order', async (length): Promise<void> => {
    const { api, state } = fixture();
    const ancestors = Array.from({ length: length - 2 }, (_, index) => ({
      id: '00000000-0000-4000-8000-' + String(index + 10).padStart(12, '0'),
      name: 'Long folder name '.repeat(10) + index,
      kind: 'directory' as const
    }));
    const items = [filesystemFixture[0], ...ancestors, filesystemFixture[2]].map(({ id, name, kind }) => ({ id, name, kind }));
    vi.spyOn(api.filesystem, 'getBreadcrumbs').mockResolvedValueOnce({ items, complete: true });
    const list = vi.spyOn(api.filesystem, 'listChildren');
    await state.select(filesystemFixture[2]);
    state.setMenuOpen(true);
    const document = documentFor(state);
    expect(document.querySelectorAll('[aria-haspopup="menu"]')).toHaveLength(length > 4 ? 1 : 0);
    if (length > 4) {
      expect(document.querySelector('button')?.getAttribute('aria-label')).toBe('Show parent folders');
      const links = Array.from(document.querySelectorAll('a[role="menuitem"]'));
      expect(links.map((link) => link.textContent)).toEqual(items.slice(1, -2).map((item) => item.name));
      expect(links.map((link) => link.getAttribute('href'))).toEqual(items.slice(1, -2).map((item) => state.href(item)));
      expect(document.querySelectorAll('.desktop-path > ol > li')).toHaveLength(4);
    }
    expect(list).not.toHaveBeenCalled();
  });

  test('partial truncation stays distinct from expandable known-ancestor overflow', async (): Promise<void> => {
    const { api, state } = fixture();
    const items = Array.from({ length: 5 }, (_, index) => ({
      id: '00000000-0000-4000-8000-' + String(index + 10).padStart(12, '0'),
      name: 'Visible ' + index,
      kind: 'directory' as const
    }));
    vi.spyOn(api.filesystem, 'getBreadcrumbs').mockResolvedValueOnce({ items, complete: false });
    await state.select(items[4]);
    state.setMenuOpen(true);
    const document = documentFor(state);
    expect(document.querySelector('.partial button, .partial a')).toBeNull();
    expect(document.querySelector('.partial')?.textContent).toContain('Earlier folders unavailable');
    expect(document.querySelectorAll('a[role="menuitem"]')).toHaveLength(2);
    expect(document.querySelector('a[href="/files"]')).toBeNull();
  });

  test.each([
    [new AuthenticationRequiredError(), 'Sign in to view the file path.', 'Sign in'],
    [new HttpError(403, 'secret', {}), 'File path unavailable.', 'Retry file path'],
    [new Error('secret'), 'File path unavailable.', 'Retry file path']
  ])('path failures have safe separate recovery', async (error, message, action): Promise<void> => {
    const { api, state } = fixture();
    vi.spyOn(api.filesystem, 'getBreadcrumbs').mockRejectedValueOnce(error);
    await state.select(filesystemFixture[2]);
    const document = documentFor(state);
    expect(document.body.textContent).toContain(message);
    expect(document.querySelector('button')?.textContent).toBe(action);
    expect(document.querySelector('a')).toBeNull();
    expect(document.body.textContent).not.toContain('secret');
  });

  test('path loading renders independently and never invents ancestors', async (): Promise<void> => {
    const { api, state } = fixture();
    const pending = deferred<Breadcrumbs>();
    vi.spyOn(api.filesystem, 'getBreadcrumbs').mockReturnValueOnce(pending.promise);
    const loading = state.select(filesystemFixture[2]);
    const document = documentFor(state);
    expect(document.body.textContent).toContain('Loading file path');
    expect(document.querySelector('a')).toBeNull();
    pending.resolve({ items: filesystemFixture.map(({ id, name, kind }) => ({ id, name, kind })), complete: true });
    await loading;
  });

  test.each(['stalled', 'failed'])('navigation renders while directory listing is %s', async (phase): Promise<void> => {
    const { api } = fixture();
    const files = new FilesState(api);
    const pending = deferred<NodeSummary[]>();
    vi.spyOn(api.filesystem, 'listChildren').mockReturnValueOnce(pending.promise);
    const loading = files.load(folderId);
    await vi.waitFor(() => expect(files.navigation.phase).toBe('ready'));
    if (phase === 'failed') {
      pending.reject(new Error('secret'));
      await loading;
    }
    const document = documentFor(files.navigation);
    expect(document.querySelector('[aria-current="page"]')?.textContent).toBe('Projects');
    expect(document.querySelector('.desktop-path a')?.getAttribute('href')).toBe('/files');
    if (phase === 'stalled') {
      pending.resolve([]);
      await loading;
    }
  });
});
