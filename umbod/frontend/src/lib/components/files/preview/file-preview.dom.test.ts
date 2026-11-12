import { InMemoryPreviewConfiguration } from '$lib/files/preview/in-memory-configuration.test-support';
import { afterEach, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { deferred, filesystemNode } from '$lib/files/fixtures.test-support';
import { FilePreviewState } from '$lib/files/preview/file-preview-state.svelte';
import { PreviewRegistry } from '$lib/files/preview/ports';
import { InMemoryFileContent } from '$lib/files/preview/in-memory-content.test-support';
import { InMemoryPublicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import { browserTransport } from '$lib/admin/infrastructure/transport';
import { FileContentRoute } from '$lib/files/infrastructure/file-content-route';
import FilePreview from './FilePreview.svelte';
import PlainPreview from './PlainPreview.test-support.svelte';
import { markdownPreviewAdapter } from './markdown-adapter';
import { pdfPreviewAdapter } from './pdf-adapter';

let component: ReturnType<typeof mount> | undefined;
let state: FilePreviewState | undefined;

afterEach(async (): Promise<void> => {
  state?.dispose();
  if (component) await unmount(component);
  state = undefined;
  component = undefined;
  document.body.replaceChildren();
});

test('renders markdown and replaces the component using an injected filetype adapter', async (): Promise<void> => {
  const source = new InMemoryFileContent(async (): Promise<string> => '# Heading');
  state = new FilePreviewState(source, new PreviewRegistry([
    { component: PlainPreview, supports: (node): boolean => node.name.endsWith('.txt'), read: (source, id, signal): Promise<string> => source.readText(id, signal) },
    markdownPreviewAdapter
  ]), new InMemoryPreviewConfiguration(257));
  component = mount(FilePreview, { target: document.body, props: { state, signIn: vi.fn() } });
  const file = filesystemNode({ name: 'notes.md', kind: 'file' });
  await state.select(file);
  await tick();
  expect(document.querySelector('article h1')?.textContent).toBe('Heading');
  await state.select({ ...file, name: 'notes.txt' });
  await tick();
  expect(document.querySelector('article')).toBeNull();
  expect(document.querySelector('pre[aria-label="Plain content"]')?.textContent).toBe('# Heading');
});

test('embeds PDF bytes and removes the viewer when selection changes', async (): Promise<void> => {
  const source = new InMemoryFileContent(async (): Promise<string> => '%PDF-1.7\nPreview');
  state = new FilePreviewState(source, new PreviewRegistry([pdfPreviewAdapter, markdownPreviewAdapter]), new InMemoryPreviewConfiguration(257));
  component = mount(FilePreview, { target: document.body, props: { state, signIn: vi.fn() } });
  const file = filesystemNode({ name: 'report.pdf', kind: 'file' });
  await state.select(file);
  await tick();
  const viewer = document.querySelector<HTMLIFrameElement>('iframe[title="PDF preview"]');
  expect(viewer).not.toBeNull();
  expect(viewer!.getAttribute('src')).toBe('data:application/pdf;base64,' + btoa('%PDF-1.7\nPreview'));
  await state.select({ ...file, name: 'notes.md' });
  await tick();
  expect(document.querySelector('iframe')).toBeNull();
  expect(document.querySelector('article')).not.toBeNull();
  state.reset();
  await tick();
  expect(document.querySelector('[aria-label="File preview"]')).toBeNull();
});

test('shows loading, forwards retry and never exposes failure details', async (): Promise<void> => {
  let attempts = 0;
  const pending = deferred<string>();
  state = new FilePreviewState(new InMemoryFileContent(async (): Promise<string> => {
    if (++attempts === 1) throw new Error('private-token');
    return pending.promise;
  }), new PreviewRegistry([markdownPreviewAdapter]), new InMemoryPreviewConfiguration(257));
  component = mount(FilePreview, { target: document.body, props: { state, signIn: vi.fn() } });
  await state.select(filesystemNode({ name: 'notes.md', kind: 'file' }));
  await tick();
  expect(document.querySelector('[role="alert"]')?.textContent).toBe("Couldn't load the preview.");
  const retry = document.querySelector<HTMLButtonElement>('button');
  expect(retry?.textContent).toBe('Retry preview');
  retry!.click();
  await tick();
  expect(document.querySelector('[role="status"]')?.textContent).toBe('Loading preview…');
  pending.resolve('Recovered');
  await vi.waitFor((): void => expect(state?.phase).toBe('ready'));
  await tick();
  expect(document.body.textContent).toContain('Recovered');
  expect(document.body.textContent).not.toContain('private-token');
});

test('too-large text reflects the same resolved limit used by the content route', async (): Promise<void> => {
  const configuration = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp', filesystemPreviewMaxBytes: 1031 });
  const request = vi.fn<typeof fetch>().mockResolvedValue(new Response('x'.repeat(1032)));
  const source = new FileContentRoute(browserTransport({ fetch: request, configuration }), configuration);
  state = new FilePreviewState(source, new PreviewRegistry([markdownPreviewAdapter]), configuration);
  component = mount(FilePreview, { target: document.body, props: { state, signIn: vi.fn() } });
  await state.select(filesystemNode({ name: 'notes.md', kind: 'file' }));
  await tick();
  expect(state.phase).toBe('too-large');
  expect(document.body.textContent).toContain('Preview is available for files up to 1031 bytes.');
  expect(document.body.textContent).not.toContain('1 MiB');
});
