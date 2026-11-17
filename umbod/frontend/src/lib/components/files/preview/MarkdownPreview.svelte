<script lang="ts">
  import type { PreviewProps } from '#lib/files/preview/ports.js';
  import { renderMarkdown } from './markdown';
  import { attachDiagrams, mermaidRenderer, type DiagramRenderer } from './mermaid';

  let { content, diagramRenderer = mermaidRenderer }: PreviewProps & { diagramRenderer?: DiagramRenderer } = $props();
</script>

<article class="markdown-preview" aria-label="Markdown content" {@attach attachDiagrams(content, diagramRenderer)}>{@html renderMarkdown(content)}</article>

<style>
  .markdown-preview { color: var(--admin-ink); line-height: 1.65; overflow-wrap: anywhere; min-width: 0; }
  .markdown-preview :global(> :first-child) { margin-top: 0; }
  .markdown-preview :global(> :last-child) { margin-bottom: 0; }
  .markdown-preview :global(a) { color: var(--admin-accent); }
  .markdown-preview :global(pre) { overflow-x: auto; padding: 1rem; border-radius: var(--admin-radius); background: var(--admin-soft); }
  .markdown-preview :global(code) { font-size: 0.9em; }
  .markdown-preview :global(blockquote) { margin-inline: 0; padding-left: 1rem; border-left: 3px solid var(--admin-border); color: var(--admin-muted); }
  .markdown-preview :global(table) { display: block; max-width: 100%; overflow-x: auto; border-collapse: collapse; }
  .markdown-preview :global(th), .markdown-preview :global(td) { padding: 0.5rem 0.75rem; border: 1px solid var(--admin-border); }
  .markdown-preview :global(hr) { border: 0; border-top: 1px solid var(--admin-border); }
  .markdown-preview :global(.hljs-keyword), .markdown-preview :global(.hljs-selector-tag), .markdown-preview :global(.hljs-tag) { color: var(--admin-accent); }
  .markdown-preview :global(.hljs-string), .markdown-preview :global(.hljs-attr), .markdown-preview :global(.hljs-bullet) { color: var(--admin-success-text); }
  .markdown-preview :global(.hljs-number), .markdown-preview :global(.hljs-literal), .markdown-preview :global(.hljs-symbol) { color: var(--admin-warning-text); }
  .markdown-preview :global(.hljs-title), .markdown-preview :global(.hljs-built_in), .markdown-preview :global(.hljs-type) { color: var(--admin-accent-strong); }
  .markdown-preview :global(.hljs-comment), .markdown-preview :global(.hljs-meta) { color: var(--admin-muted); }
  .markdown-preview :global(.hljs-section), .markdown-preview :global(.hljs-strong) { font-weight: 600; }
  .markdown-preview :global(.hljs-emphasis) { font-style: italic; }
  .markdown-preview :global(.mermaid-diagram) { max-width: 100%; overflow-x: auto; margin-block: 1rem; }
  .markdown-preview :global(.mermaid-diagram > svg) { display: block; max-width: 100%; height: auto; margin-inline: auto; }
</style>
