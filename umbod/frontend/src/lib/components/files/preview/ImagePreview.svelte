<script lang="ts">
  import type { PreviewProps } from '$lib/files/preview/ports';

  let { content, onError }: PreviewProps = $props();
</script>

<div class="image-preview">
  {#key content}
    <img
      src={content}
      alt="File preview"
      onerror={(event): void => { if (event.currentTarget.isConnected) onError?.(); }}
      referrerpolicy="no-referrer"
    />
  {/key}
</div>

<style>
  .image-preview {
    display: flex;
    justify-content: center;
    padding: 1rem;
    border: 1px solid var(--admin-border);
    border-radius: 0.5rem;
  }

  img {
    display: block;
    max-width: 100%;
    max-height: 70vh;
    object-fit: contain;
  }
</style>
