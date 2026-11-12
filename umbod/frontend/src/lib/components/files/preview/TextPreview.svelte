<script lang="ts">
  import type { PreviewProps } from '$lib/files/preview/ports';

  let { content }: PreviewProps = $props();
</script>

<pre class="text-preview" aria-label="Text content">{content}</pre>

<style>
  .text-preview {
    margin: 0;
    min-width: 0;
    max-width: 100%;
    padding: 1rem;
    border-radius: var(--admin-radius);
    background: var(--admin-soft);
    color: var(--admin-ink);
    font-family: monospace;
    font-size: 0.9rem;
    line-height: 1.65;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    tab-size: 4;
  }
</style>
