<script lang="ts">
  import type { PreviewProps } from '$lib/files/preview/ports';

  let { content }: PreviewProps = $props();
</script>

<iframe title="PDF preview" src={content} referrerpolicy="no-referrer"></iframe>

<style>
  iframe {
    display: block;
    width: 100%;
    height: 70vh;
    min-height: 24rem;
    border: 0;
    border-radius: 0.5rem;
  }
</style>
