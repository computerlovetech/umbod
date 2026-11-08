<script lang="ts">
  import { fileTypeIcon } from './file-type-icons';

  let { kind, name, contentType, size = 20 }: {
    kind: 'file' | 'directory';
    name: string;
    contentType?: unknown;
    size?: number;
  } = $props();
</script>

<svg role="img" aria-label={fileTypeIcon(kind, name, contentType).label} focusable="false" viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  {#each fileTypeIcon(kind, name, contentType).paths as path (path)}
    <path d={path} />
  {/each}
</svg>

<style>
  svg { flex-shrink: 0; }
</style>
