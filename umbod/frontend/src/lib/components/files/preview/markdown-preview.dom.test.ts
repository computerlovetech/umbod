import { afterEach, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import MarkdownPreview from './MarkdownPreview.svelte';
import { attachDiagrams, type DiagramRenderer } from './mermaid';
import { renderMarkdown } from './markdown';

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
});

function mountPreview(content: string, renderer: DiagramRenderer): void {
  component = mount(MarkdownPreview, { target: document.body, props: { content, diagramRenderer: renderer } });
}

const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 40"><text>A to B</text></svg>';

test('renders highlighted Markdown and never invokes diagrams for ordinary fences', async (): Promise<void> => {
  const render = vi.fn<DiagramRenderer['render']>();
  mountPreview('# Title\n\n~~~ts\nconst value = "safe";\n~~~\n\n~~~unknown\n<img src=x>\n~~~', { render });
  await tick();
  expect(document.querySelector('h1')?.textContent).toBe('Title');
  expect(document.querySelector('.hljs-keyword')?.textContent).toBe('const');
  expect(document.querySelectorAll('pre')[1].textContent).toBe('<img src=x>\n');
  expect(document.querySelector('img')).toBeNull();
  expect(render).not.toHaveBeenCalled();
});

test('shows the document body without front-matter headings or separators', async (): Promise<void> => {
  const render = vi.fn<DiagramRenderer['render']>();
  mountPreview('---\ntype: Product Proposal\ntitle: Hidden title\nstatus: draft\n---\n\n# Umbod Enterprise Cloud\n\nExecutive proposal', { render });
  await tick();
  expect(document.querySelector('article')?.textContent).toBe('Umbod Enterprise Cloud\nExecutive proposal\n');
  expect(document.querySelector('h1')?.textContent).toBe('Umbod Enterprise Cloud');
  expect(document.querySelector('h2, hr')).toBeNull();
  expect(render).not.toHaveBeenCalled();
});

test('replaces a mermaid fence with an accessible diagram and preserves other code', async (): Promise<void> => {
  const render = vi.fn<DiagramRenderer['render']>().mockResolvedValue(svg);
  mountPreview('~~~mermaid\ngraph TD; A-->B\n~~~\n\n~~~plaintext\nunchanged\n~~~', { render });
  await vi.waitFor((): void => { expect(document.querySelector('svg[aria-label="Mermaid diagram"]')).not.toBeNull(); });
  expect(render).toHaveBeenCalledWith('graph TD; A-->B\n');
  expect(document.querySelector('svg')?.textContent).toBe('A to B');
  expect(document.querySelector('pre')?.textContent).toBe('unchanged\n');
});

test.each(['reject', 'invalid', 'large', 'complex'])('keeps escaped source when rendering is %s', async (failure: string): Promise<void> => {
  const render = vi.fn<DiagramRenderer['render']>();
  if (failure === 'reject') render.mockRejectedValue(new Error('Invalid diagram'));
  else if (failure === 'invalid') render.mockResolvedValue('<div>not SVG</div>');
  else render.mockResolvedValue('<svg>' + (failure === 'complex' ? '<g></g>'.repeat(2001) : 'x'.repeat(250001)) + '</svg>');
  mountPreview('~~~mermaid\ngraph TD; A-->B\n~~~', { render });
  await tick();
  await Promise.resolve();
  await Promise.resolve();
  expect(render).toHaveBeenCalledOnce();
  expect(document.querySelector('[data-mermaid] pre')?.textContent).toBe('graph TD; A-->B\n');
  expect(document.querySelector('svg')).toBeNull();
});

test.each([
  '%% Diagram comment\nflowchart TD; A[Click here]-->B[Follow the link]',
  'sequenceDiagram\nAlice->>Bob: Click the link',
  'graph TD; A-->B; classDef highlighted fill:#f9f,stroke:#333; class A highlighted'
])('renders legitimate labels, comments and bounded styles', async (source: string): Promise<void> => {
  const render = vi.fn<DiagramRenderer['render']>().mockResolvedValue(svg);
  mountPreview('~~~mermaid\n' + source + '\n~~~', { render });
  await vi.waitFor((): void => { expect(document.querySelector('svg')).not.toBeNull(); });
  expect(render).toHaveBeenCalledWith(source + '\n');
});

test('rejects unsafe source before invoking the rendering boundary', async (): Promise<void> => {
  const render = vi.fn<DiagramRenderer['render']>();
  const source = 'graph TD; A[<img src="https://tracker.invalid">]; click A callback';
  mountPreview('~~~mermaid\n' + source + '\n~~~', { render });
  await tick();
  expect(render).not.toHaveBeenCalled();
  expect(document.querySelector('pre')?.textContent).toBe(source + '\n');
  expect(document.querySelector('img, a, svg')).toBeNull();
});

test('removes interactions, external resources and HTML from returned SVG', async (): Promise<void> => {
  const unsafe = '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><text>Safe</text><a href="https://tracker.invalid"><text>Link</text></a><image href="https://tracker.invalid/pixel"/><foreignObject><div>HTML</div></foreignObject><script>alert(1)</script><style>@import "https://tracker.invalid/style";</style><rect onclick="alert(1)" fill="url(https://tracker.invalid)"/></svg>';
  mountPreview('~~~mermaid\ngraph TD; A-->B\n~~~', { render: async (): Promise<string> => unsafe });
  await vi.waitFor((): void => { expect(document.querySelector('svg')).not.toBeNull(); });
  expect(document.querySelector('a, image, foreignObject, script, style, [onload], [onclick], [href], [fill]')).toBeNull();
  expect(document.querySelector('svg')?.textContent).toBe('Safe');
});

test('preserves safe local SVG marker references', async (): Promise<void> => {
  const marked = '<svg xmlns="http://www.w3.org/2000/svg"><defs><marker id="arrow"><path d="M0,0 L1,1"/></marker></defs><path marker-end="url(&quot;#arrow&quot;)" d="M0,0 L10,10"/></svg>';
  mountPreview('~~~mermaid\ngraph TD; A-->B\n~~~', { render: async (): Promise<string> => marked });
  await vi.waitFor((): void => { expect(document.querySelector('[marker-end]')).not.toBeNull(); });
  expect(document.querySelector('[marker-end]')?.getAttribute('marker-end')).toBe('url("#arrow")');
});

test('does not insert a diagram after component disposal', async (): Promise<void> => {
  let resolve: (value: string) => void = (): void => {};
  const pending = new Promise<string>((complete: (value: string) => void): void => { resolve = complete; });
  mountPreview('~~~mermaid\ngraph TD; A-->B\n~~~', { render: (): Promise<string> => pending });
  await tick();
  const target = document.querySelector('[data-mermaid]');
  expect(target).not.toBeNull();
  await unmount(component!);
  component = undefined;
  resolve(svg);
  await pending;
  expect(target?.querySelector('svg')).toBeNull();
  expect(document.querySelector('svg')).toBeNull();
});

test('fences obsolete results when attachment content is replaced', async (): Promise<void> => {
  const element = document.createElement('article');
  document.body.append(element);
  element.innerHTML = renderMarkdown('~~~mermaid\ngraph TD; A-->B\n~~~');
  let resolve: (value: string) => void = (): void => {};
  const pending = new Promise<string>((complete: (value: string) => void): void => { resolve = complete; });
  const dispose = attachDiagrams('old', { render: (): Promise<string> => pending })(element);
  if (typeof dispose !== 'function') throw new Error('Missing attachment cleanup');
  dispose();
  element.innerHTML = renderMarkdown('# Replacement');
  resolve(svg);
  await pending;
  expect(element.querySelector('svg')).toBeNull();
  expect(element.textContent).toBe('Replacement\n');
});
