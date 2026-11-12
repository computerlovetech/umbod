<script lang="ts">
  import type { PreviewProps } from '$lib/files/preview/ports';
  import { renderMarkdown } from './markdown';

  let { content }: PreviewProps = $props();
</script>

<article class="markdown-preview" aria-label="Markdown content">{@html renderMarkdown(content)}</article>

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
</style>
