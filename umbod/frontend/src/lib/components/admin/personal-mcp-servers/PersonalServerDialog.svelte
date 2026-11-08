<script lang="ts">
  import ModalShell from '$lib/components/shared/ModalShell.svelte';
  import type { Snippet } from 'svelte';
  import { modalDialog } from './modal-dialog';

  let { title, titleId, descriptionId, close, children }: {
    title: string;
    titleId: string;
    descriptionId: string;
    close: () => void;
    children: Snippet;
  } = $props();
</script>

<ModalShell {title} {titleId} {descriptionId} {close} dialogAttachment={modalDialog(close, 'mcp-workspace-heading')}>
  {@render children()}
</ModalShell>
