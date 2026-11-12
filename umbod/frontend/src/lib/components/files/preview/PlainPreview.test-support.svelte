<script lang="ts">
  import type { PreviewProps } from '$lib/files/preview/ports';
  let { content }: PreviewProps = $props();
</script>

<pre aria-label="Plain content">{content}</pre>
