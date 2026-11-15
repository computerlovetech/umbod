import { describe, expect, test } from 'vitest';
import { renderMarkdown } from './markdown';
import { isSafeDiagramSource } from './mermaid';

describe('fenced syntax highlighting', (): void => {
  test.each([
    ['ts', 'const value: string = "safe"'],
    ['js', 'const value = "safe"'],
    ['json', '{"value": true}'],
    ['python', 'def value(): return True'],
    ['bash', 'echo "$HOME"'],
    ['yaml', 'value: true'],
    ['css', 'body { color: red; }'],
    ['html', '<div>safe</div>'],
    ['sql', 'SELECT value FROM data'],
    ['markdown', '# Heading']
  ])('highlights the explicit %s grammar', (language: string, source: string): void => {
    const html = renderMarkdown('~~~' + language + '\n' + source + '\n~~~');
    expect(html).toContain('class="hljs"');
    expect(html).toContain('<span class="hljs-');
  });

  test.each(['unknown', '', 'plaintext', 'mermaid'])('keeps %s code escaped', (language: string): void => {
    const html = renderMarkdown('~~~' + language + '\n<script>alert("unsafe")</script>\n~~~');
    expect(html).not.toContain('<script>');
    expect(html).toContain('&lt;script&gt;');
  });

  test('falls back for oversized code and limits the cumulative highlighting budget', (): void => {
    expect(renderMarkdown('~~~js\n' + 'const x = 1;'.repeat(2000) + '\n~~~')).not.toContain('<span');
    const block = '~~~js\n' + 'const x = 1;'.repeat(1500) + '\n~~~\n';
    expect(renderMarkdown(block.repeat(7)).match(/class="hljs"/g)).toHaveLength(5);
  });

  test('limits diagram count without losing source', (): void => {
    const html = renderMarkdown('~~~mermaid\ngraph TD; A-->B\n~~~\n'.repeat(10));
    expect(html.match(/data-mermaid/g)).toHaveLength(8);
    expect(html.match(/A--&gt;B/g)).toHaveLength(10);
  });
});

describe('diagram source limits', (): void => {
  test.each([
    'graph TD; A-->B',
    'sequenceDiagram\nAlice->>Bob: Hello',
    'classDiagram\nAnimal <|-- Duck',
    'stateDiagram-v2\n[*] --> Ready',
    'erDiagram\nCUSTOMER ||--o{ ORDER : places',
    'pie\n"A" : 10',
    'flowchart TD\nA[Click here] --> B[Follow the link]',
    'flowchart TD\nA[Click; then follow the link] --> B',
    'sequenceDiagram\nAlice->>Bob: Click the link',
    'sequenceDiagram\nClick->>Bob: Hello',
    'graph TD; click --> B',
    'graph TD; A[Don\'t click the link] --> B',
    '%% A harmless diagram comment\n%% More context\ngraph TD; A-->B',
    'graph TD; A-->B; classDef highlighted fill:#f9f,stroke:#333,stroke-width:2px; class A highlighted',
    'graph TD; A-->B; style A fill:rgb(255,0,0),stroke:#333; linkStyle 0 stroke:red,stroke-width:2px'
  ])('accepts bounded diagram source %s', (source: string): void => {
    expect(isSafeDiagramSource(source)).toBe(true);
  });

  test.each([
    'graph TD; A[<img src=x onerror=alert(1)>]',
    'graph TD; A[https://tracker.invalid]',
    'graph TD; click A callback',
    'graph TD; click A "https://example.org"',
    'graph TD; A@{ img: "pixel" }',
    'graph TD; A[&lt;script&gt;]',
    'graph TD; A[![image](pixel)]',
    'graph TD; style A fill:url(pixel)',
    'graph TD; classDef remote fill:url(../pixel)',
    'graph TD; classDef remote fill:uRl("pixel")',
    'graph TD; classDef remote fill:red; @import "local.css"',
    'graph TD; classDef remote background-image:pixel',
    'graph TD\nA[Safe]\nclick A callback',
    'classDiagram\nclass Animal\nlink Animal "relative-page"',
    '%% Comment\n%%{init: {"securityLevel":"loose"}}%%\ngraph TD; A-->B',
    '%% Comment\n---\nconfig:\n  securityLevel: loose\n---\ngraph TD; A-->B',
    '%%{init: {"securityLevel":"loose"}}%%\ngraph TD; A-->B',
    '---\nconfig:\n  securityLevel: loose\n---\ngraph TD; A-->B',
    'unsupported diagram',
    'graph TD; A[' + 'x'.repeat(8000) + ']',
    'graph TD\n' + 'A-->B\n'.repeat(121),
    'graph TD; ' + 'A-->B;'.repeat(101)
  ])('rejects unsafe or expensive source', (source: string): void => {
    expect(isSafeDiagramSource(source)).toBe(false);
  });
});
