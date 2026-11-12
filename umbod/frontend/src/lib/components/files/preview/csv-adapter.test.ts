import { expect, test } from 'vitest';
import { fileId, filesystemNode } from '$lib/files/fixtures.test-support';
import { InMemoryFileContent } from '$lib/files/preview/in-memory-content.test-support';
import { PreviewRegistry } from '$lib/files/preview/ports';
import { csvPreviewAdapter } from './csv-adapter';
import { textPreviewAdapter } from './text-adapter';

test.each<[string, string | undefined, boolean]>([
  ['data', 'text/csv', true],
  ['data', 'application/csv', true],
  ['data', ' TEXT/CSV; charset=utf-8', true],
  ['data', 'APPLICATION/CSV; charset=utf-8', true],
  ['DATA.CSV', undefined, true],
  ['data.csv', '', true],
  ['data.csv', 'application/octet-stream', true],
  ['data.csv', 'text/plain; charset=utf-8', true],
  ['data.csv', 'application/pdf', false],
  ['data.csv', 'text/html', false],
  ['data.csv', 'text/markdown', false],
  ['data.csv', 'application/yaml', false],
  ['data.csv.txt', undefined, false],
  ['data', undefined, false],
  ['data.txt', 'text/plain', false],
  ['data.bin', 'application/octet-stream', false]
])('selects %s with MIME %s as CSV: %s', (name: string, mime: string | undefined, supported: boolean): void => {
  const file = filesystemNode({ id: fileId, name, kind: 'file', metadata: { content_type: mime ?? {}, attributes: {} } });
  expect(csvPreviewAdapter.supports(file)).toBe(supported);
});

test('selects CSV ahead of the plain-text fallback for text/plain CSV files', (): void => {
  const registry = new PreviewRegistry([csvPreviewAdapter, textPreviewAdapter]);
  const file = filesystemNode({ id: fileId, name: 'data.csv', kind: 'file', metadata: { content_type: 'text/plain', attributes: {} } });
  expect(registry.resolve(file)).toBe(csvPreviewAdapter);
});

test.each(['', '\uFEFFname,value\r\n"日本語","line one\nline two"', '"unterminated'])('reads CSV unchanged through the content port: %j', async (content: string): Promise<void> => {
  const source = new InMemoryFileContent(async (): Promise<string> => content);
  const signal = new AbortController().signal;
  expect(await csvPreviewAdapter.read(source, fileId, signal)).toBe(content);
  expect(source.requests).toEqual([{ id: fileId, signal }]);
});
