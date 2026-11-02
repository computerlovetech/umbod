<script lang="ts">
  import Button from '$lib/components/admin/shared/Button.svelte';
  import { filesystemConfirmation } from './confirmation-dialog';
  let { title, description, confirmLabel, oncancel, onconfirm }: {
    title: string;
    description: string;
    confirmLabel: string;
    oncancel: () => void;
    onconfirm: () => void;
  } = $props();
</script>

<dialog aria-labelledby="filesystem-confirmation-title" aria-describedby="filesystem-confirmation-description" {@attach filesystemConfirmation(oncancel)}>
  <h2 id="filesystem-confirmation-title">{title}</h2>
  <p id="filesystem-confirmation-description">{description}</p>
  <div class="actions">
    <Button variant="secondary" type="button" data-dialog-cancel onclick={(event) => { event.currentTarget.closest('dialog')?.close(); oncancel(); }}>Cancel</Button>
    <Button variant="primary" type="button" onclick={(event) => { event.currentTarget.closest('dialog')?.close(); onconfirm(); }}>{confirmLabel}</Button>
  </div>
</dialog>

<style>
  dialog { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius-panel); box-shadow: var(--admin-shadow-dialog); box-sizing: border-box; color: var(--admin-ink); max-height: calc(100dvh - 2rem); max-width: 36rem; overflow: auto; padding: 1.5rem; width: calc(100% - 2rem); }
  dialog::backdrop { background: var(--admin-overlay); }
  h2 { font-size: 1.25rem; margin-top: 0; }
  p { color: var(--admin-muted); line-height: 1.6; }
  .actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 1rem; margin-top: 1rem; }
</style>
