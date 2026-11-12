import { describe, expect, test } from 'vitest';
import { filesystemNode } from '$lib/files/fixtures.test-support';
import { renderMarkdown } from './markdown';
import { markdownPreviewAdapter } from './markdown-adapter';

describe('markdown preview adapter', (): void => {
  test.each([
    ['notes.MD', '', true],
    ['notes.markdown', 'text/plain; charset=utf-8', true],
    ['notes', 'Text/Markdown; charset=utf-8', true],
    ['notes', 'text/x-markdown', true],
    ['notes.md', 'image/png', false],
    ['notes.txt', 'text/plain', false]
  ])('selects %s with MIME %s', (name: string, mime: string, supported: boolean): void => {
    expect(markdownPreviewAdapter.supports(filesystemNode({ name, kind: 'file', metadata: { content_type: mime, attributes: {} } }))).toBe(supported);
  });

  test('renders headings, lists, emphasis, code, quotes and tables', (): void => {
    const html = renderMarkdown('# Title\n\n- **Bold** and *emphasis*\n\n> Quote\n\n~~~ts\nconst x = 1;\n~~~\n\n| A | B |\n| - | - |\n| 1 | 2 |');
    for (const tag of ['<h1>', '<ul>', '<strong>', '<em>', '<blockquote>', '<pre>', '<table>']) expect(html).toContain(tag);
  });

  test('escapes raw HTML, SVG, scripts and code without enabling execution', (): void => {
    const html = renderMarkdown('<script>alert(1)</script>\n\n<svg onload=alert(1)>\n\n`<img onerror=alert(1)>`');
    expect(html).not.toMatch(/<(script|svg|img)\b/i);
    expect(html).toContain('&lt;script&gt;');
  });

  test('blocks unsafe, relative and protocol-relative links and all image requests', (): void => {
    for (const url of ['javascript:alert(1)', 'data:text/html,hello', '/files', '../notes.md', '//tracker.invalid']) {
      expect(renderMarkdown('[link](' + url + ')')).not.toContain('href=');
    }
    const html = renderMarkdown('![private image](https://tracker.invalid/pixel)\n\n[Safe](https://example.org)\n\n[Mail](mailto:user@example.org)');
    expect(html).not.toContain('<img');
    expect(html).toContain('private image');
    expect(html).toContain('href="https://example.org"');
    expect(html).toContain('href="mailto:user@example.org"');
  });
});
