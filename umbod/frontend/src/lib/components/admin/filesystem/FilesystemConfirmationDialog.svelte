<script lang="ts">
  import Button from '$lib/components/admin/shared/Button.svelte';
  import ModalShell from '$lib/components/shared/ModalShell.svelte';
  import { filesystemConfirmation } from './confirmation-dialog';
  let { title, description, confirmLabel, oncancel, onconfirm }: {
    title: string;
    description: string;
    confirmLabel: string;
    oncancel: () => void;
    onconfirm: () => void;
  } = $props();
</script>

<ModalShell {title} titleId="filesystem-confirmation-title" descriptionId="filesystem-confirmation-description" close={oncancel} dialogAttachment={filesystemConfirmation(oncancel)} --modal-overflow="auto">
  <p id="filesystem-confirmation-description">{description}</p>
  <div class="actions">
    <Button variant="secondary" type="button" data-dialog-cancel onclick={(event) => { event.currentTarget.closest('dialog')?.close(); oncancel(); }}>Cancel</Button>
    <Button variant="primary" type="button" onclick={(event) => { event.currentTarget.closest('dialog')?.close(); onconfirm(); }}>{confirmLabel}</Button>
  </div>
</ModalShell>

<style>
  p { color: var(--admin-muted); line-height: 1.6; }
  .actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 1rem; margin-top: 1rem; }
</style>
