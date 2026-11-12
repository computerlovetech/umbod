import { InMemoryPreviewConfiguration } from '$lib/files/preview/in-memory-configuration.test-support';
import { afterEach, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { filesystemNode } from '$lib/files/fixtures.test-support';
import { FilePreviewState } from '$lib/files/preview/file-preview-state.svelte';
import { InMemoryFileContent } from '$lib/files/preview/in-memory-content.test-support';
import { PreviewRegistry } from '$lib/files/preview/ports';
import FilePreview from './FilePreview.svelte';
import { imagePreviewAdapter } from './image-adapter';
import { markdownPreviewAdapter } from './markdown-adapter';

let component: ReturnType<typeof mount> | undefined;
let state: FilePreviewState | undefined;

const png = new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10, 0, 255, 128]);
const file = filesystemNode({ name: 'photo.png', kind: 'file' });

afterEach(async (): Promise<void> => {
  state?.dispose();
  if (component) await unmount(component);
  state = undefined;
  component = undefined;
  document.body.replaceChildren();
});

test('renders image bytes with accessible alternative text and removes the image on navigation', async (): Promise<void> => {
  const source = new InMemoryFileContent(async (): Promise<Uint8Array> => png);
  state = new FilePreviewState(source, new PreviewRegistry([imagePreviewAdapter]), new InMemoryPreviewConfiguration(257));
  component = mount(FilePreview, { target: document.body, props: { state, signIn: vi.fn() } });
  await state.select(file);
  await tick();
  const image = document.querySelector<HTMLImageElement>('img[alt="File preview"]');
  expect(image).not.toBeNull();
  expect(image!.getAttribute('src')).toBe('data:image/png;base64,' + btoa(String.fromCharCode(...png)));
  state.reset();
  await tick();
  expect(document.querySelector('img')).toBeNull();
});

test('replaces image content without retaining the previous source', async (): Promise<void> => {
  const jpeg = new Uint8Array([255, 216, 255, 224]);
  const source = new InMemoryFileContent(async (id: string): Promise<Uint8Array> => id === file.id ? png : jpeg);
  state = new FilePreviewState(source, new PreviewRegistry([imagePreviewAdapter]), new InMemoryPreviewConfiguration(257));
  component = mount(FilePreview, { target: document.body, props: { state, signIn: vi.fn() } });
  await state.select(file);
  await tick();
  const previousImage = document.querySelector('img');
  expect(previousImage).not.toBeNull();
  await state.select({ ...file, id: '00000000-0000-4000-8000-000000000099', name: 'photo.jpg' });
  await tick();
  expect(document.querySelector('img')?.getAttribute('src')).toBe('data:image/jpeg;base64,' + btoa(String.fromCharCode(...jpeg)));
  previousImage!.dispatchEvent(new Event('error'));
  await tick();
  expect(state.phase).toBe('ready');
  expect(document.querySelector('img')?.getAttribute('src')).toBe('data:image/jpeg;base64,' + btoa(String.fromCharCode(...jpeg)));
});

test('image decoding failures show a retry action that reloads the image', async (): Promise<void> => {
  const source = new InMemoryFileContent(async (): Promise<Uint8Array> => png);
  state = new FilePreviewState(source, new PreviewRegistry([imagePreviewAdapter]), new InMemoryPreviewConfiguration(257));
  component = mount(FilePreview, { target: document.body, props: { state, signIn: vi.fn() } });
  await state.select(file);
  await tick();
  const image = document.querySelector('img');
  expect(image).not.toBeNull();
  image!.dispatchEvent(new Event('error'));
  await tick();
  expect(document.querySelector('img')).toBeNull();
  expect(document.querySelector('[role="alert"]')?.textContent).toBe("Couldn't load the preview.");
  const retry = document.querySelector<HTMLButtonElement>('button');
  expect(retry?.textContent).toBe('Retry preview');
  retry!.click();
  await vi.waitFor((): void => expect(state?.phase).toBe('ready'));
  await tick();
  expect(source.requests).toHaveLength(2);
  expect(document.querySelector('img')).not.toBeNull();
});

test('switching from an image to Markdown replaces the renderer', async (): Promise<void> => {
  const source = new InMemoryFileContent(async (id: string): Promise<string | Uint8Array> => id === file.id ? png : '# Notes');
  state = new FilePreviewState(source, new PreviewRegistry([imagePreviewAdapter, markdownPreviewAdapter]), new InMemoryPreviewConfiguration(257));
  component = mount(FilePreview, { target: document.body, props: { state, signIn: vi.fn() } });
  await state.select(file);
  await tick();
  await state.select({ ...file, id: '00000000-0000-4000-8000-000000000099', name: 'notes.md' });
  await tick();
  expect(document.querySelector('img')).toBeNull();
  expect(document.querySelector('article h1')?.textContent).toBe('Notes');
});
