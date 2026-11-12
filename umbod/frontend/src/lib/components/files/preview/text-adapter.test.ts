import { expect, test } from 'vitest';
import { fileId, filesystemNode } from '$lib/files/fixtures.test-support';
import { InMemoryFileContent } from '$lib/files/preview/in-memory-content.test-support';
import { PreviewRegistry } from '$lib/files/preview/ports';
import { markdownPreviewAdapter } from './markdown-adapter';
import { textPreviewAdapter } from './text-adapter';

test.each<[string, string | undefined, boolean]>([
  ['notes.txt', 'text/plain', true],
  ['notes', 'TEXT/PLAIN; charset=utf-8', true],
  ['NOTES.TXT', undefined, true],
  ['notes.txt', 'application/octet-stream', true],
  ['config', 'application/yaml', true],
  ['config', 'application/x-yaml', true],
  ['config', 'text/yaml', true],
  ['config', 'TEXT/X-YAML; charset=utf-8', true],
  ['config', 'application/toml', true],
  ['config', 'APPLICATION/X-TOML; charset=utf-8', true],
  ['config', 'text/toml', true],
  ['config', 'text/x-toml', true],
  ['events', 'TEXT/X-LOG; charset=utf-8', true],
  ['config.yaml', undefined, true],
  ['CONFIG.YML', undefined, true],
  ['CONFIG.TOML', undefined, true],
  ['events.log', undefined, true],
  ['config.yaml', 'application/octet-stream', true],
  ['config.yml', 'application/octet-stream', true],
  ['config.toml', 'application/octet-stream', true],
  ['events.log', 'application/octet-stream', true],
  ['config.yaml', 'text/html', false],
  ['config.yml', 'application/pdf', false],
  ['config.toml', 'application/json', false],
  ['events.log', 'image/png', false],
  ['config.yaml.bak', undefined, false],
  ['notes.txt', 'text/html', false],
  ['notes.txt', 'application/pdf', false],
  ['notes.txt', 'image/png', false],
  ['notes.txt', 'text/markdown', false],
  ['notes.md', undefined, false],
  ['image.svg', 'image/svg+xml', false],
  ['data.bin', 'application/octet-stream', false],
  ['notes', undefined, false]
])('selects %s with MIME %s as text: %s', (name: string, mime: string | undefined, supported: boolean): void => {
  const file = filesystemNode({ name, kind: 'file', metadata: { content_type: mime ?? {}, attributes: {} } });
  expect(textPreviewAdapter.supports(file)).toBe(supported);
});

test('keeps Markdown rendering ahead of the plain text fallback', (): void => {
  const registry = new PreviewRegistry([markdownPreviewAdapter, textPreviewAdapter]);
  const file = filesystemNode({ name: 'notes.md', kind: 'file', metadata: { content_type: 'text/plain', attributes: {} } });
  expect(registry.resolve(file)).toBe(markdownPreviewAdapter);
});

test.each(['', '  First line\n\tSecond line — 日本語\n<script>alert(1)</script>'])('reads text unchanged through the content port', async (value: string): Promise<void> => {
  const source = new InMemoryFileContent(async (): Promise<string> => value);
  const signal = new AbortController().signal;
  expect(await textPreviewAdapter.read(source, fileId, signal)).toBe(value);
  expect(source.requests).toEqual([{ id: fileId, signal }]);
});
