<script lang="ts">
  import Button from '$lib/components/admin/shared/Button.svelte';
  import ModalShell from '$lib/components/shared/ModalShell.svelte';
  import type { DeletionState } from '$lib/files/state/deletion-state.svelte';

  let { state, oncancel = () => state.cancel(), onconfirm = () => { void state.confirm(); } }: { state: DeletionState; oncancel?: () => void; onconfirm?: () => void } = $props();
</script>

<ModalShell title={`Delete “${state.confirmation?.name}”?`} titleId="file-deletion-title" descriptionId="file-deletion-description" close={oncancel} --modal-overflow="auto">
  <p id="file-deletion-description">This permanently removes “{state.confirmation?.name}” from the workspace. There is no restore.</p>
  <div class="actions">
    <Button variant="secondary" type="button" data-dialog-cancel onclick={oncancel}>Cancel</Button>
    <Button variant="danger" type="button" onclick={onconfirm}>Delete file</Button>
  </div>
</ModalShell>

<style>
  p { overflow-wrap: anywhere; }
  p { line-height: 1.6; }
  .actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 1rem; }
  :focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
</style>
