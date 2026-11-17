import { afterEach, describe, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { AuthenticationRequiredError, HttpError } from '#lib/admin/infrastructure/transport.js';
import { deferred, filesystemNode, rootId, folderId, fileId } from '#lib/files/fixtures.test-support.js';
import { InMemoryFilesApi } from '#lib/files/infrastructure/in-memory-api.test-support.js';
import { FilesState, filesHref } from '#lib/files/state/files-state.svelte.js';
import { NewFolderState } from '#lib/files/state/new-folder-state.svelte.js';
import { UploadState } from '#lib/files/state/upload-state.svelte.js';
import type { BrowseResult, FilesystemNamespace } from '#lib/files/domain/schemas.js';
import { FilePreviewState } from '#lib/files/preview/file-preview-state.svelte.js';
import { InMemoryPreviewConfiguration } from '#lib/files/preview/in-memory-configuration.test-support.js';
import { InMemoryFileContent } from '#lib/files/preview/in-memory-content.test-support.js';
import { PreviewRegistry } from '#lib/files/preview/ports.js';
import { textPreviewAdapter } from './preview/text-adapter';
import FilesContent from './FilesContent.svelte';

let component: ReturnType<typeof mount> | undefined;
let files: FilesState | undefined;
let folder: NewFolderState | undefined;
let upload: UploadState | undefined;

afterEach(async (): Promise<void> => {
  upload?.dispose();
  folder?.dispose();
  files?.dispose();
  if (component) await unmount(component);
  component = undefined;
  files = undefined;
  folder = undefined;
  upload = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

function setup(sharedName: string = 'Research', preview?: FilePreviewState): { api: InMemoryFilesApi; state: FilesState; inventory: FilesystemNamespace[]; signIn: ReturnType<typeof vi.fn> } {
  const api = new InMemoryFilesApi(rootId, [
    filesystemNode(),
    filesystemNode({ id: folderId, parent_id: rootId, name: 'Research' }),
    filesystemNode({ id: fileId, parent_id: folderId, name: 'Report.txt', kind: 'file' })
  ]);
  const inventory: FilesystemNamespace[] = [
    { id: rootId, root_node_id: rootId, name: 'Internal personal name', kind: 'personal', description: '', permissions: ['discover', 'read'] },
    { id: folderId, root_node_id: folderId, name: sharedName, kind: 'shared', description: '', permissions: ['discover', 'read'] }
  ];
  vi.spyOn(api.filesystem, 'listNamespaces').mockResolvedValue(inventory);
  const state = new FilesState(api, undefined, preview);
  files = state;
  folder = new NewFolderState(api, state);
  upload = new UploadState(api, state);
  const signIn = vi.fn();
  const target = document.createElement('div');
  document.body.append(target);
  component = mount(FilesContent, { target, props: { state, folder, upload, signIn } });
  return { api, state, inventory, signIn };
}

function locations(): HTMLElement {
  const navigation = document.querySelector<HTMLElement>('nav[aria-label="File locations"]');
  expect(navigation).not.toBeNull();
  return navigation!;
}

function link(id: string): HTMLAnchorElement {
  const anchor = locations().querySelector<HTMLAnchorElement>(`a[href="${filesHref(id)}"]`);
  expect(anchor).not.toBeNull();
  return anchor!;
}

function recoveryButton(label: string): HTMLButtonElement {
  const button = Array.from(locations().querySelectorAll('button')).find((candidate) => candidate.textContent?.trim() === label);
  expect(button).toBeDefined();
  return button!;
}

describe('Files locations panel', (): void => {
  test('initial discovery shows the existing loading overlay only in the files pane', async (): Promise<void> => {
    vi.useFakeTimers();
    const { api, state, inventory } = setup();
    const listing = deferred<FilesystemNamespace[]>();
    vi.mocked(api.filesystem.listNamespaces).mockReturnValueOnce(listing.promise);
    const loading = state.load(null);
    await tick();
    vi.advanceTimersByTime(300);
    await tick();
    const detail = document.querySelector('[aria-label="Files content"]');
    expect(locations().textContent).not.toContain('Loading');
    expect(locations().querySelector('[role="status"], .delayed-spinner')).toBeNull();
    expect(detail?.querySelector('.delayed-loading-overlay__scrim .delayed-spinner__mark')).not.toBeNull();
    expect(detail?.querySelector('[inert][aria-busy="true"]')).not.toBeNull();
    listing.resolve(inventory);
    await loading;
    await tick();
    expect(detail?.querySelector('.delayed-loading-overlay__scrim')).toBeNull();
    expect(locations().querySelectorAll('a')).toHaveLength(2);
  });

  test('renders grouped native links, selected decorative checks and escaped wrapping labels reactively', async (): Promise<void> => {
    const name = '<img src=x onerror=alert(1)> &' + 'LongNamespace'.repeat(20);
    const { api, state, inventory } = setup(name);
    await state.load(null);
    await tick();
    expect(document.querySelector('aside[aria-label="Locations"]')).not.toBeNull();
    expect(Array.from(locations().querySelectorAll('h2')).map((heading) => heading.textContent)).toEqual(['Personal', 'Shared namespaces']);
    expect(link(rootId).textContent?.trim()).toBe('My files');
    expect(link(rootId).getAttribute('aria-current')).toBe('page');
    expect(link(rootId).querySelectorAll('svg[aria-hidden="true"]')).toHaveLength(2);
    expect(link(folderId).textContent?.trim()).toBe(name);
    expect(link(folderId).hasAttribute('aria-current')).toBe(false);
    expect(locations().querySelector('img, select, button')).toBeNull();
    expect(locations().textContent).not.toContain('Internal personal name');
    const personalLink = link(rootId);
    await state.load(fileId);
    await tick();
    expect(link(rootId)).toBe(personalLink);
    expect(link(folderId).getAttribute('aria-current')).toBe('page');
    expect(link(folderId).querySelectorAll('svg[aria-hidden="true"]')).toHaveLength(2);
    expect(link(rootId).hasAttribute('aria-current')).toBe(false);
    vi.mocked(api.filesystem.listNamespaces).mockResolvedValue([{ ...inventory[1], name: 'Renamed shared namespace' }]);
    await state.reload();
    await tick();
    expect(locations().querySelectorAll('h2')).toHaveLength(1);
    expect(locations().textContent).not.toContain('Personal');
    expect(locations().textContent).not.toContain('My files');
    expect(link(folderId).textContent?.trim()).toBe('Renamed shared namespace');
  });

  test('a single personal entry still renders the panel without an empty Shared heading', async (): Promise<void> => {
    const { api, state, inventory } = setup();
    vi.mocked(api.filesystem.listNamespaces).mockResolvedValue([inventory[0]]);
    await state.load(null);
    await tick();
    expect(locations().querySelectorAll('a')).toHaveLength(1);
    expect(locations().querySelector('h2')?.textContent).toBe('Personal');
    expect(locations().textContent).not.toContain('Shared');
    expect(link(rootId).getAttribute('aria-current')).toBe('page');
  });

  test('retains the rail, links, detail and heading across pending discovery, browse, file detail and error', async (): Promise<void> => {
    const { api, state, inventory } = setup();
    await state.load(folderId);
    await tick();
    const rail = document.querySelector('aside');
    const navigation = locations();
    const sharedLink = link(folderId);
    const detail = document.querySelector('[aria-label="Files content"]');
    const container = document.querySelector('.page-container');
    const heading = document.querySelector('#files-heading');
    const header = heading?.closest('header');
    const toolbar = document.querySelector('[aria-label="Location actions"]');
    const workspace = document.querySelector('[aria-label="Files workspace"]');
    expect(header).not.toBeNull();
    expect(toolbar).not.toBeNull();
    expect(workspace).not.toBeNull();
    expect(header?.contains(toolbar)).toBe(true);
    expect(header!.compareDocumentPosition(workspace!) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(workspace?.contains(header ?? null)).toBe(false);
    expect(workspace?.contains(toolbar)).toBe(false);
    expect(toolbar?.querySelector('#upload-file-button, #new-folder-button')).not.toBeNull();
    const result = await api.filesystem.browse(fileId);
    const listing = deferred<FilesystemNamespace[]>();
    const browse = deferred<BrowseResult>();
    vi.mocked(api.filesystem.listNamespaces).mockReturnValueOnce(listing.promise);
    vi.spyOn(api.filesystem, 'browse').mockReturnValueOnce(browse.promise);
    const loading = state.load(fileId);
    await tick();
    expect(locations().textContent).not.toContain('Loading locations');
    expect(link(folderId)).toBe(sharedLink);
    expect(sharedLink.getAttribute('aria-current')).toBe('page');
    expect(detail?.textContent).toContain('Loading files');
    const retainedButtons = toolbar!.querySelectorAll<HTMLButtonElement>('#upload-file-button, #new-folder-button');
    expect(retainedButtons).toHaveLength(2);
    expect(Array.from(retainedButtons).every((button) => button.disabled)).toBe(true);
    expect(detail?.querySelector('[inert][aria-busy="true"]')).not.toBeNull();
    listing.resolve(inventory);
    await vi.waitFor((): void => expect(state.discoveryPhase).toBe('ready'));
    await tick();
    expect(locations().textContent).not.toContain('Loading locations');
    expect(detail?.textContent).toContain('Loading files');
    browse.resolve(result);
    await loading;
    await tick();
    expect(detail?.querySelector('[aria-label="Metadata"]')).not.toBeNull();
    vi.mocked(api.filesystem.browse).mockRejectedValueOnce(new HttpError(403, 'Private diagnostic', {}));
    await state.reload();
    await tick();
    expect(detail?.textContent).toContain("You don't have access to this location.");
    expect(locations().querySelector('[aria-current]')).toBeNull();
    expect(document.querySelector('aside')).toBe(rail);
    expect(locations()).toBe(navigation);
    expect(link(folderId)).toBe(sharedLink);
    expect(document.querySelector('[aria-label="Files content"]')).toBe(detail);
    expect(document.querySelector('.page-container')).toBe(container);
    expect(document.querySelector('#files-heading')).toBe(heading);
    expect(heading?.closest('header')).toBe(header);
    expect(document.querySelector('[aria-label="Location actions"]')).toBe(toolbar);
    expect(workspace?.contains(header ?? null)).toBe(false);
    expect(workspace?.contains(toolbar)).toBe(false);
  });

  test.each([
    [new Error('Private diagnostic'), "Couldn't load locations.", 'Retry locations'],
    [new HttpError(403, 'Private diagnostic', {}), "You don't have access to the locations list.", 'Retry locations'],
    [new AuthenticationRequiredError(), 'Sign in to view locations.', 'Sign in']
  ])('discovery recovery keeps direct UUID browsing independent', async (error, message, action): Promise<void> => {
    const { api, state, signIn } = setup();
    vi.mocked(api.filesystem.listNamespaces).mockRejectedValueOnce(error);
    await state.load(fileId);
    await tick();
    expect(state.phase).toBe('ready');
    expect(locations().textContent).toContain(message);
    expect(locations().querySelector('a, h2')).toBeNull();
    expect(document.body.textContent).not.toContain('Private diagnostic');
    recoveryButton(action).click();
    if (action === 'Sign in') expect(signIn).toHaveBeenCalledOnce();
    else {
      await vi.waitFor((): void => expect(state.discoveryPhase).toBe('ready'));
      await tick();
      expect(link(folderId).getAttribute('aria-current')).toBe('page');
    }
  });

  test('preview loading, content and failure never remount the locations or detail frame', async (): Promise<void> => {
    const content = deferred<string>();
    const preview = new FilePreviewState(new InMemoryFileContent((): Promise<string> => content.promise), new PreviewRegistry([textPreviewAdapter]), new InMemoryPreviewConfiguration(1024));
    const { state } = setup('Research', preview);
    await state.load(folderId);
    await tick();
    const rail = document.querySelector('aside');
    const shared = link(folderId);
    const detail = document.querySelector('.page-container');
    const listHeaders = Array.from(document.querySelectorAll('thead th'), (heading) => heading.textContent).slice(0, 3);
    const rowLink = document.querySelector(`tbody a[href="${filesHref(fileId)}"]`);
    expect(rowLink).not.toBeNull();
    const listedTimestamp = rowLink!.closest('tr')!.querySelector('time')?.textContent;
    expect(listHeaders).toEqual(['Name', 'Type', 'Updated']);
    await state.load(fileId);
    await tick();
    expect(document.querySelector('[aria-label="Files content"]')?.textContent).toContain('Loading preview');
    expect(document.querySelector('[aria-label="Metadata"]')).toBeNull();
    expect(document.querySelector('[aria-label="File preview"]')).toBeNull();
    expect(document.querySelector('.file-preview-surface')).toBeNull();
    expect(document.querySelector('[inert][aria-busy="true"]')).not.toBeNull();
    content.resolve('Preview content');
    await vi.waitFor((): void => expect(preview.phase).toBe('ready'));
    await tick();
    expect(document.querySelector('pre[aria-label="Text content"]')?.textContent).toBe('Preview content');
    const metadata = document.querySelector('[aria-label="Metadata"]');
    const rendered = document.querySelector('[aria-label="File preview"]');
    expect(metadata).not.toBeNull();
    expect(rendered).not.toBeNull();
    const surface = metadata!.closest('.file-preview-surface');
    expect(document.querySelector('[aria-label="Files content"] .files-view')?.contains(surface)).toBe(true);
    expect(surface?.querySelector(':scope > .preview-document')?.contains(rendered)).toBe(true);
    expect(metadata!.nextElementSibling?.contains(rendered)).toBe(true);
    expect(metadata!.querySelector('h2')).toBeNull();
    expect(Array.from(metadata!.querySelectorAll('.metadata-grid dt'), (label) => label.textContent)).toEqual(listHeaders);
    expect(metadata!.querySelector('time')?.textContent).toBe(listedTimestamp);
    expect(metadata!.querySelector('.metadata-filename')?.textContent).toBe('Report.txt');
    expect(metadata!.compareDocumentPosition(rendered!) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(document.querySelector('[inert][aria-busy="true"]')).toBeNull();
    preview.createRenderErrorHandler()();
    await tick();
    expect(document.querySelector('[aria-label="File preview"]')?.textContent).toContain("Couldn't load the preview.");
    expect(document.querySelector('aside')).toBe(rail);
    expect(link(folderId)).toBe(shared);
    expect(shared.getAttribute('aria-current')).toBe('page');
    expect(document.querySelector('.page-container')).toBe(detail);
  });

  test.each([
    ['empty', '', 'This file is empty.'],
    ['error', undefined, "Couldn't load the preview."]
  ])('metadata appears above the %s preview outcome after the spinner', async (_outcome: string, result: string | undefined, message: string): Promise<void> => {
    vi.useFakeTimers();
    const content = deferred<string>();
    const preview = new FilePreviewState(new InMemoryFileContent((): Promise<string> => content.promise), new PreviewRegistry([textPreviewAdapter]), new InMemoryPreviewConfiguration(1024));
    const { state } = setup('Research', preview);
    await state.load(fileId);
    await tick();
    await vi.advanceTimersByTimeAsync(300);
    await tick();
    expect(document.querySelector('[aria-label="Metadata"]')).toBeNull();
    expect(document.querySelector('.delayed-loading-overlay__scrim .delayed-spinner__mark')).not.toBeNull();
    if (result === undefined) content.reject(new Error('Private diagnostic'));
    else content.resolve(result);
    await vi.waitFor((): void => expect(preview.phase).not.toBe('loading'));
    await tick();
    const metadata = document.querySelector('[aria-label="Metadata"]');
    const rendered = document.querySelector('[aria-label="File preview"]');
    expect(metadata).not.toBeNull();
    expect(rendered?.textContent).toContain(message);
    expect(metadata!.compareDocumentPosition(rendered!) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(document.querySelector('.delayed-loading-overlay__scrim')).toBeNull();
    expect(document.body.textContent).not.toContain('Private diagnostic');
  });

  test.each([
    ['text/plain', 'Text file'],
    [{}, 'Text file'],
    ['application/pdf', 'PDF file'],
    ['image/png', 'Image file']
  ])('compact metadata preserves file properties and literal attributes with MIME %s', async (contentType: string | Record<string, never>, typeLabel: string): Promise<void> => {
    const { api, state } = setup();
    const result = await api.filesystem.browse(fileId);
    const name = '<img src=x>-' + 'Long file name '.repeat(8) + '.txt';
    vi.spyOn(api.filesystem, 'browse').mockResolvedValueOnce({ ...result, breadcrumbs: { ...result.breadcrumbs, items: result.breadcrumbs.items.map((item) => item.id === fileId ? { ...item, name } : item) }, node: { ...result.node, name, metadata: { content_type: contentType, attributes: { checksum: '<svg onload=alert(1)>', description: 'Private guidance' } } } });
    await state.load(fileId);
    await tick();
    const metadata = document.querySelector('[aria-label="Metadata"]');
    expect(metadata).not.toBeNull();
    expect(metadata!.querySelector('.metadata-filename')?.textContent).toBe(name);
    expect(metadata!.querySelector('.metadata-filename')?.getAttribute('title')).toBe(name);
    const typeValue = metadata!.querySelectorAll('.metadata-grid dd')[1];
    expect(typeValue.textContent).toBe(typeLabel);
    expect(typeValue.getAttribute('title')).toBe(typeof contentType === 'string' ? contentType : null);
    expect(metadata!.querySelector('.metadata-icon[aria-hidden="true"] svg')?.getAttribute('aria-label')).toBe(typeLabel);
    expect(metadata!.querySelector('time')?.getAttribute('datetime')).toBe(result.node.updated_at);
    expect(metadata!.querySelector('time')?.getAttribute('title')).toBe(result.node.updated_at);
    expect(metadata!.querySelector('time')?.textContent).toContain('UTC');
    expect(metadata!.querySelector('.metadata-attributes dt')?.textContent).toBe('checksum');
    expect(metadata!.querySelector('.metadata-attributes dd')?.textContent).toBe('<svg onload=alert(1)>');
    expect(metadata!.textContent).not.toContain('Private guidance');
    expect(metadata!.querySelector('h2, img, [onload]')).toBeNull();
    expect(metadata!.querySelectorAll('svg')).toHaveLength(1);
  });

  test('retry hides metadata until the replacement preview has downloaded', async (): Promise<void> => {
    const replacement = deferred<string>();
    let attempts = 0;
    const source = new InMemoryFileContent(async (): Promise<string> => {
      if (++attempts === 1) throw new Error('Temporary failure');
      return replacement.promise;
    });
    const preview = new FilePreviewState(source, new PreviewRegistry([textPreviewAdapter]), new InMemoryPreviewConfiguration(1024));
    const { state } = setup('Research', preview);
    await state.load(fileId);
    await vi.waitFor((): void => expect(preview.phase).toBe('error'));
    await tick();
    expect(document.querySelector('[aria-label="Metadata"]')).not.toBeNull();
    const retry = Array.from(document.querySelectorAll('button')).find((button) => button.textContent?.trim() === 'Retry preview');
    expect(retry).toBeDefined();
    retry!.click();
    await tick();
    expect(document.querySelector('[aria-label="Metadata"]')).toBeNull();
    expect(document.querySelector('[aria-label="File preview"]')).toBeNull();
    expect(document.querySelector('[inert][aria-busy="true"]')).not.toBeNull();
    replacement.resolve('Recovered content');
    await vi.waitFor((): void => expect(preview.phase).toBe('ready'));
    await tick();
    expect(document.querySelector('[aria-label="Metadata"]')).not.toBeNull();
    expect(document.querySelector('pre[aria-label="Text content"]')?.textContent).toBe('Recovered content');
  });

  test('unsupported files show metadata and the preview outcome without waiting for content', async (): Promise<void> => {
    const source = new InMemoryFileContent(async (): Promise<string> => 'Unused content');
    const preview = new FilePreviewState(source, new PreviewRegistry([]), new InMemoryPreviewConfiguration(1024));
    const { state } = setup('Research', preview);
    await state.load(fileId);
    await tick();
    expect(state.contentLoading).toBe(false);
    expect(document.querySelector('[aria-label="Metadata"]')).not.toBeNull();
    expect(document.querySelector('[aria-label="File preview"]')?.textContent).toContain('Preview is not available for this file type.');
    expect(source.requests).toHaveLength(0);
  });

  test('successful empty discovery is not an error or a fabricated personal location', async (): Promise<void> => {
    const { api, state } = setup();
    vi.mocked(api.filesystem.listNamespaces).mockResolvedValue([]);
    await state.load(fileId);
    await tick();
    expect(locations().textContent).toContain('No locations available.');
    expect(locations().querySelector('a, h2, button, [role="alert"]')).toBeNull();
    expect(document.querySelector('#files-heading')?.textContent).toBe('Files');
  });
});
