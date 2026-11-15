import { afterEach, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import MarkdownPreview from './MarkdownPreview.svelte';
import { mermaidRenderer } from './mermaid';

const library = vi.hoisted(() => ({
  loaded: vi.fn<() => void>(),
  initialize: vi.fn<(configuration: unknown) => void>(),
  render: vi.fn<(id: string, source: string, container: Element) => Promise<{ svg: string }>>()
}));

vi.mock('mermaid', () => {
  library.loaded();
  return { default: { initialize: library.initialize, render: library.render } };
});

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

test('loads Mermaid only for a safe mermaid fence and configures strict sanitized rendering', async (): Promise<void> => {
  component = mount(MarkdownPreview, { target: document.body, props: { content: '~~~js\nconst x = 1;\n~~~' } });
  await tick();
  expect(library.loaded).not.toHaveBeenCalled();
  await unmount(component);
  component = mount(MarkdownPreview, { target: document.body, props: { content: '~~~mermaid\ngraph TD; click A callback\n~~~' } });
  await tick();
  expect(library.loaded).not.toHaveBeenCalled();
  await unmount(component);
  library.render.mockResolvedValue({ svg: '<svg xmlns="http://www.w3.org/2000/svg"><text>Diagram</text></svg>' });
  component = mount(MarkdownPreview, { target: document.body, props: { content: '~~~mermaid\ngraph TD; A-->B\n~~~' } });
  await vi.waitFor((): void => { expect(document.querySelector('svg[role="img"]')).not.toBeNull(); });
  expect(library.loaded).toHaveBeenCalledOnce();
  expect(library.initialize).toHaveBeenCalledWith(expect.objectContaining({ securityLevel: 'strict', htmlLabels: false, startOnLoad: false, suppressErrorRendering: true, maxTextSize: 8000, maxEdges: 100, flowchart: { htmlLabels: false } }));
  expect(library.render).toHaveBeenCalledWith(expect.stringMatching(/^preview-diagram-\d+$/), 'graph TD; A-->B\n', expect.any(HTMLElement));
  expect(document.body.children).toHaveLength(1);
});

test('cleans temporary rendering DOM after Mermaid rejects invalid syntax', async (): Promise<void> => {
  library.render.mockImplementation(async (_id: string, _source: string, container: Element): Promise<{ svg: string }> => {
    container.append(document.createElement('svg'));
    throw new Error('Invalid syntax');
  });
  await expect(mermaidRenderer.render('graph TD; invalid[')).rejects.toThrow('Invalid syntax');
  expect(document.body.children).toHaveLength(0);
});

test('rejects unsafe source even when called outside an attachment', async (): Promise<void> => {
  const calls = library.render.mock.calls.length;
  await expect(mermaidRenderer.render('graph TD; A[https://tracker.invalid]')).rejects.toThrow('Unsupported diagram');
  expect(library.render.mock.calls).toHaveLength(calls);
});
