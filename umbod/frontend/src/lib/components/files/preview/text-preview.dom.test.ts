import { afterEach, expect, test } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { fileId, folderId, filesystemNode } from '$lib/files/fixtures.test-support';
import { FilePreviewState } from '$lib/files/preview/file-preview-state.svelte';
import { InMemoryPreviewConfiguration } from '$lib/files/preview/in-memory-configuration.test-support';
import { InMemoryFileContent } from '$lib/files/preview/in-memory-content.test-support';
import { PreviewRegistry } from '$lib/files/preview/ports';
import FilePreview from './FilePreview.svelte';
import { textPreviewAdapter } from './text-adapter';

let component: ReturnType<typeof mount> | undefined;
let state: FilePreviewState | undefined;

afterEach(async (): Promise<void> => {
  state?.dispose();
  if (component) await unmount(component);
  state = undefined;
  component = undefined;
  document.body.replaceChildren();
});

test.each(['txt', 'yaml', 'yml', 'toml', 'log'])('renders .%s literally, preserves whitespace and replaces content on selection', async (extension: string): Promise<void> => {
  const content = '  Hello 日本語\n\t<script>alert(1)</script>\n<img src="https://example.com/private">\n# Not Markdown\n';
  const source = new InMemoryFileContent(async (id: string): Promise<string> => id === fileId ? content : 'Replacement');
  state = new FilePreviewState(source, new PreviewRegistry([textPreviewAdapter]), new InMemoryPreviewConfiguration(1024));
  component = mount(FilePreview, { target: document.body, props: { state, signIn: (): void => {} } });
  await state.select(filesystemNode({ id: fileId, name: `notes.${extension}`, kind: 'file' }));
  await tick();
  expect(document.querySelector('pre[aria-label="Text content"]')?.textContent).toBe(content);
  expect(document.querySelector('script, img, h1, textarea, [contenteditable]')).toBeNull();
  await state.select(filesystemNode({ id: folderId, name: `other.${extension}`, kind: 'file' }));
  await tick();
  expect(document.querySelector('pre')?.textContent).toBe('Replacement');
  state.reset();
  await tick();
  expect(document.querySelector('pre')).toBeNull();
});

test.each(['txt', 'yaml', 'yml', 'toml', 'log'])('shows the existing empty-file state for an empty .%s file', async (extension: string): Promise<void> => {
  state = new FilePreviewState(new InMemoryFileContent(async (): Promise<string> => ''), new PreviewRegistry([textPreviewAdapter]), new InMemoryPreviewConfiguration(1024));
  component = mount(FilePreview, { target: document.body, props: { state, signIn: (): void => {} } });
  await state.select(filesystemNode({ id: fileId, name: `empty.${extension}`, kind: 'file' }));
  await tick();
  expect(document.querySelector('[role="status"]')?.textContent).toBe('This file is empty.');
  expect(document.querySelector('pre')).toBeNull();
});

test.each(['txt', 'yaml', 'yml', 'toml', 'log'])('does not read or render .%s without read permission', async (extension: string): Promise<void> => {
  const source = new InMemoryFileContent(async (): Promise<string> => 'Private');
  state = new FilePreviewState(source, new PreviewRegistry([textPreviewAdapter]), new InMemoryPreviewConfiguration(1024));
  component = mount(FilePreview, { target: document.body, props: { state, signIn: (): void => {} } });
  const file = filesystemNode({ id: fileId, name: `private.${extension}`, kind: 'file' });
  await state.select({ ...file, permissions: { ...file.permissions, can_read: false } });
  await tick();
  expect(source.requests).toEqual([]);
  expect(document.querySelector('[aria-label="File preview"]')).toBeNull();
});
