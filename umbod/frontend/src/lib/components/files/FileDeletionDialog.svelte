<script lang="ts">
  import { nativeDialog } from '$lib/components/shared/dialogs/native-dialog';
  import type { DeletionState } from '$lib/files/state/deletion-state.svelte';

  let { state, oncancel = () => state.cancel(), onconfirm = () => { void state.confirm(); } }: { state: DeletionState; oncancel?: () => void; onconfirm?: () => void } = $props();
</script>

<dialog aria-labelledby="file-deletion-title" aria-describedby="file-deletion-description" {@attach nativeDialog(oncancel)}>
  <h2 id="file-deletion-title">Delete “{state.confirmation?.name}”?</h2>
  <p id="file-deletion-description">This permanently removes “{state.confirmation?.name}” from the workspace. There is no restore.</p>
  <div class="actions">
    <button type="button" data-dialog-cancel onclick={oncancel}>Cancel</button>
    <button type="button" class="danger" onclick={onconfirm}>Delete file</button>
  </div>
</dialog>

<style>
  dialog { text-align: left; box-sizing: border-box; width: min(36rem, calc(100% - 2rem)); max-height: calc(100dvh - 2rem); overflow: auto; padding: 1.5rem; background: var(--admin-panel); color: var(--admin-ink); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); box-shadow: var(--admin-shadow-dialog); }
  dialog::backdrop { background: var(--admin-overlay); }
  h2, p { overflow-wrap: anywhere; }
  p { line-height: 1.6; }
  .actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 1rem; }
  button { padding: 0.6rem 0.9rem; background: var(--admin-panel); color: var(--admin-ink); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); font: inherit; cursor: pointer; }
  .danger { background: var(--admin-danger); border-color: var(--admin-danger); color: var(--admin-panel); }
  :focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
</style>
