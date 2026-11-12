import { afterEach, expect, test } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { fileId, folderId, filesystemNode } from '$lib/files/fixtures.test-support';
import { FilePreviewState } from '$lib/files/preview/file-preview-state.svelte';
import { InMemoryPreviewConfiguration } from '$lib/files/preview/in-memory-configuration.test-support';
import { InMemoryFileContent } from '$lib/files/preview/in-memory-content.test-support';
import { PreviewRegistry } from '$lib/files/preview/ports';
import FilePreview from './FilePreview.svelte';
import { csvPreviewAdapter } from './csv-adapter';
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

test('renders generated column headers, all data rows and literal values, then replaces the selection', async (): Promise<void> => {
  const content = 'name,value\r\n日本語,"line one\nline two"\r\n=SUM(A1:A2),<img src="https://example.com/private">';
  const source = new InMemoryFileContent(async (id: string): Promise<string> => id === fileId ? content : 'replacement,42,extra');
  state = new FilePreviewState(source, new PreviewRegistry([csvPreviewAdapter, textPreviewAdapter]), new InMemoryPreviewConfiguration(4096));
  component = mount(FilePreview, { target: document.body, props: { state, signIn: (): void => {} } });
  await state.select(filesystemNode({ id: fileId, name: 'data.csv', kind: 'file', metadata: { content_type: 'text/plain', attributes: {} } }));
  await tick();
  expect(document.querySelector('table[aria-label="CSV content"]')).not.toBeNull();
  expect(Array.from(document.querySelectorAll('th'), (cell: Element): string | null => cell.textContent)).toEqual(['Column 1', 'Column 2']);
  expect(Array.from(document.querySelectorAll('tbody td'), (cell: Element): string | null => cell.textContent)).toEqual([
    'name', 'value', '日本語', 'line one\nline two', '=SUM(A1:A2)', '<img src="https://example.com/private">'
  ]);
  expect(document.querySelector('img, script, pre, [role="status"]')).toBeNull();
  await state.select(filesystemNode({ id: folderId, name: 'other.csv', kind: 'file' }));
  await tick();
  expect(Array.from(document.querySelectorAll('th'), (cell: Element): string | null => cell.textContent)).toEqual(['Column 1', 'Column 2', 'Column 3']);
  expect(Array.from(document.querySelectorAll('tbody td'), (cell: Element): string | null => cell.textContent)).toEqual(['replacement', '42', 'extra']);
  expect(document.body.textContent).not.toContain('日本語');
  state.reset();
  await tick();
  expect(document.querySelector('table, [aria-label="File preview"]')).toBeNull();
});

test('falls back to literal text for malformed quotes and removes the fallback on valid CSV selection', async (): Promise<void> => {
  const malformed = '"unterminated,<script>alert(1)</script>\n  private';
  const source = new InMemoryFileContent(async (id: string): Promise<string> => id === fileId ? malformed : 'valid,data');
  state = new FilePreviewState(source, new PreviewRegistry([csvPreviewAdapter]), new InMemoryPreviewConfiguration(4096));
  component = mount(FilePreview, { target: document.body, props: { state, signIn: (): void => {} } });
  await state.select(filesystemNode({ id: fileId, name: 'broken.csv', kind: 'file' }));
  await tick();
  expect(document.querySelector('[role="status"]')?.textContent).toBe('This CSV could not be displayed as a table. Showing plain text.');
  expect(document.querySelector('pre[aria-label="Text content"]')?.textContent).toBe(malformed);
  expect(document.querySelector('table, script')).toBeNull();
  await state.select(filesystemNode({ id: folderId, name: 'valid.csv', kind: 'file' }));
  await tick();
  expect(document.querySelector('table')).not.toBeNull();
  expect(document.querySelector('pre, [role="status"]')).toBeNull();
});

test.each<[number, number, boolean]>([[200, 50, false], [201, 2, true], [2, 51, true]])('renders bounded CSV for %i rows and %i columns with truncation status %s', async (rows: number, columns: number, truncated: boolean): Promise<void> => {
  const content = Array.from({ length: rows }, (_value: unknown, row: number): string => Array.from({ length: columns }, (_cell: unknown, column: number): string => `${row + 1}:${column + 1}`).join(',')).join('\n');
  state = new FilePreviewState(new InMemoryFileContent(async (): Promise<string> => content), new PreviewRegistry([csvPreviewAdapter]), new InMemoryPreviewConfiguration(100000));
  component = mount(FilePreview, { target: document.body, props: { state, signIn: (): void => {} } });
  await state.select(filesystemNode({ id: fileId, name: 'large.csv', kind: 'file' }));
  await tick();
  expect(document.querySelectorAll('tbody tr')).toHaveLength(Math.min(rows, 200));
  expect(document.querySelectorAll('th')).toHaveLength(Math.min(columns, 50));
  expect(document.querySelector('tbody tr:last-child td:last-child')?.textContent).toBe(`${Math.min(rows, 200)}:${Math.min(columns, 50)}`);
  if (truncated) {
    expect(document.querySelector('[role="status"]')?.textContent).toBe('Preview limited to the first 200 rows and 50 columns.');
  } else {
    expect(document.querySelector('[role="status"]')).toBeNull();
  }
});

test('uses the existing empty-file state for empty CSV', async (): Promise<void> => {
  state = new FilePreviewState(new InMemoryFileContent(async (): Promise<string> => ''), new PreviewRegistry([csvPreviewAdapter]), new InMemoryPreviewConfiguration(4096));
  component = mount(FilePreview, { target: document.body, props: { state, signIn: (): void => {} } });
  await state.select(filesystemNode({ id: fileId, name: 'empty.csv', kind: 'file' }));
  await tick();
  expect(document.querySelector('[role="status"]')?.textContent).toBe('This file is empty.');
  expect(document.querySelector('table, pre')).toBeNull();
});

test('does not read or render CSV without read permission', async (): Promise<void> => {
  const source = new InMemoryFileContent(async (): Promise<string> => 'private,data');
  state = new FilePreviewState(source, new PreviewRegistry([csvPreviewAdapter]), new InMemoryPreviewConfiguration(4096));
  component = mount(FilePreview, { target: document.body, props: { state, signIn: (): void => {} } });
  const file = filesystemNode({ id: fileId, name: 'private.csv', kind: 'file' });
  await state.select({ ...file, permissions: { ...file.permissions, can_read: false } });
  await tick();
  expect(source.requests).toEqual([]);
  expect(document.querySelector('[aria-label="File preview"], table, pre')).toBeNull();
});
