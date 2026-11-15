import type { Attachment } from 'svelte/attachments';

export interface DiagramRenderer {
  render(source: string): Promise<string>;
}

function diagramStatements(source: string): string[] {
  const statements: string[] = [];
  let statement = '';
  let quote = '';
  let depth = 0;
  for (const character of source) {
    if (quote) {
      if (character === quote) quote = '';
    } else if (character === '"') quote = character;
    else if ('[({'.includes(character)) depth++;
    else if ('])}'.includes(character)) depth = Math.max(0, depth - 1);
    if (!quote && depth === 0 && (character === '\n' || character === ';')) {
      statements.push(statement.trim());
      statement = '';
    } else statement += character;
  }
  statements.push(statement.trim());
  return statements;
}

function isSafeDiagramStatement(statement: string): boolean {
  if (/^(?:click|links?|callback|image|icon|href)\s+(?![-=.<>|])\S/i.test(statement)) return false;
  if (!/^(?:style|classDef|linkStyle)\b/i.test(statement)) return true;
  const declaration = /^(?:style|classDef|linkStyle)\s+[\w,:-]+\s+(.+)$/i.exec(statement);
  if (!declaration) return false;
  return declaration[1].split(/,(?![^(]*\))/).every((property: string): boolean => {
    const match = /^\s*([\w-]+)\s*:\s*([#\w.,%()\s-]+)\s*$/.exec(property);
    return match !== null && /^(?:fill|stroke|stroke-width|color|font-size|font-weight|font-style|stroke-dasharray|opacity|fill-opacity|stroke-opacity|rx|ry)$/i.test(match[1]);
  });
}

export function isSafeDiagramSource(source: string): boolean {
  if (source.length > 8000) return false;
  const diagram = source.split('\n').filter((line: string): boolean => !/^\s*%%/.test(line)).join('\n');
  return source.split('\n').length <= 120
    && source.split(/\s+|[;{}]/).length <= 1000
    && (source.match(/--|==|\.\./g)?.length ?? 0) <= 100
    && /^\s*(?:flowchart\b|graph\b|sequenceDiagram\b|classDiagram\b|stateDiagram(?:-v2)?\b|erDiagram\b|pie\b|journey\b|timeline\b)/.test(diagram)
    && !/%%\s*\{|^\s*---|<\s*[a-z!/]|(?:https?:|ftp:|data:|javascript:|\/\/)|&(?:#\w+|\w+);|\]\s*\(|!\[|@|\\|\b(?:url|expression)\s*\(/im.test(source)
    && diagramStatements(diagram).every(isSafeDiagramStatement);
}

let nextDiagramId = 0;

export const mermaidRenderer: DiagramRenderer = {
  async render(source: string): Promise<string> {
    if (!isSafeDiagramSource(source)) throw new Error('Unsupported diagram');
    const { default: mermaid } = await import('mermaid');
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'strict',
      htmlLabels: false,
      suppressErrorRendering: true,
      maxTextSize: 8000,
      maxEdges: 100,
      flowchart: { htmlLabels: false },
      secure: ['securityLevel', 'startOnLoad', 'maxTextSize', 'maxEdges', 'htmlLabels', 'suppressErrorRendering', 'secure']
    });
    const container = document.createElement('div');
    container.style.position = 'absolute';
    container.style.visibility = 'hidden';
    container.style.pointerEvents = 'none';
    container.setAttribute('aria-hidden', 'true');
    document.body.append(container);
    try {
      const { svg } = await mermaid.render('preview-diagram-' + ++nextDiagramId, source, container);
      return svg;
    } finally {
      container.remove();
    }
  }
};

function hasExternalStyleReference(style: string): boolean {
  return /@import|url\s*\(/i.test(style.replace(/url\(\s*(['"]?)#[\w:.-]+\1\s*\)/gi, ''));
}

function diagramSvg(svg: string): SVGSVGElement {
  if (svg.length > 250000) throw new Error('Diagram too large');
  const template = document.createElement('template');
  template.innerHTML = svg;
  const root = template.content.firstElementChild;
  if (!(root instanceof SVGSVGElement) || template.content.childElementCount !== 1 || root.querySelectorAll('*').length > 2000) {
    throw new Error('Invalid diagram');
  }
  for (const element of [root, ...root.querySelectorAll('*')]) {
    if (['a', 'image', 'foreignobject', 'script', 'iframe', 'object', 'embed', 'animate', 'set', 'animatetransform'].includes(element.localName.toLowerCase())) {
      element.remove();
      continue;
    }
    for (const attribute of Array.from(element.attributes)) {
      if (/^on/i.test(attribute.name) || /href$/i.test(attribute.name) || hasExternalStyleReference(attribute.value)) element.removeAttribute(attribute.name);
    }
    if (element.localName === 'style' && hasExternalStyleReference(element.textContent ?? '')) element.remove();
  }
  root.setAttribute('role', 'img');
  root.setAttribute('aria-label', 'Mermaid diagram');
  return root;
}

export function attachDiagrams(_content: string, renderer: DiagramRenderer = mermaidRenderer): Attachment<HTMLElement> {
  return (element: HTMLElement): (() => void) => {
    let disposed = false;
    const originals = Array.from(element.querySelectorAll<HTMLElement>('[data-mermaid]'), (target: HTMLElement): { target: HTMLElement; children: Node[] } => ({ target, children: Array.from(target.childNodes) }));
    for (const { target } of originals) {
      const source = target.textContent ?? '';
      if (!isSafeDiagramSource(source)) continue;
      void renderer.render(source).then((svg: string): void => {
        if (!disposed) target.replaceChildren(diagramSvg(svg));
      }).catch((): void => {});
    }
    return (): void => {
      disposed = true;
      for (const { target, children } of originals) target.replaceChildren(...children);
    };
  };
}
