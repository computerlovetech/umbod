import { describe, expect, test } from 'vitest';
import { filesystemNode } from '#lib/files/fixtures.test-support.js';
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

  test.each([
    '---\ntype: Product Proposal\ntitle: Hidden title\nstatus: draft\n---\n',
    '\uFEFF---\r\ntitle: Hidden title\r\ntags:\r\n  - draft\r\n---\r\n',
    '--- \ntitle: Hidden title\n...\n',
    '---\n---\n'
  ])('omits leading front matter and renders only the document body', (frontMatter: string): void => {
    const body = '# Umbod Enterprise Cloud\n\nExecutive proposal\n\n---\n\nSection\n---\n';
    expect(renderMarkdown(frontMatter + body)).toBe(renderMarkdown(body));
  });

  test.each(['---\ntitle: Hidden title\n---', '---\ntitle: Hidden title\n...\n'])('renders metadata-only documents without leaking front matter', (content: string): void => {
    expect(renderMarkdown(content)).toBe('');
  });

  test.each([
    ['---\ntitle: Unfinished\n\n# Body', 'Unfinished'],
    ['# Body\n\n---\ntitle: Body content\n---', 'Body content'],
    ['~~~plaintext\n---\ntitle: Code sample\n---\n~~~', 'title: Code sample'],
    ['Section\n---\n\nBody', '<h2>Section</h2>'],
    ['---\n\nBody', '<hr>']
  ])('preserves ordinary Markdown and incomplete front matter', (content: string, expected: string): void => {
    expect(renderMarkdown(content)).toContain(expected);
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
