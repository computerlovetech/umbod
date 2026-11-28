<script lang="ts">
  import Button from './Button.svelte';

  let { busy, dirty, conflict = false, saveDisabled = false, saveButtonId, statusId, onDiscard, onSave }: {
    busy: boolean;
    dirty: boolean;
    conflict?: boolean;
    saveDisabled?: boolean;
    saveButtonId?: string;
    statusId?: string;
    onDiscard: () => void;
    onSave: () => void | Promise<void>;
  } = $props();
</script>

<div class="actions">
  <p id={statusId} tabindex="-1" role="status">{busy ? 'Saving changes…' : dirty || conflict ? 'Unsaved changes' : 'No unsaved changes'}</p>
  <div class="buttons">
    {#if dirty || conflict}
      <Button variant="secondary" disabled={busy} onclick={onDiscard}>Discard changes</Button>
    {/if}
    <Button id={saveButtonId} disabled={busy || !dirty || conflict || saveDisabled} onclick={onSave}>Save changes</Button>
  </div>
</div>

<style>
  .actions { align-items: center; display: flex; flex-wrap: wrap; gap: 1rem; justify-content: space-between; margin-top: 1rem; }
  p { color: var(--admin-muted); font-size: 13px; line-height: 1.5; margin: 0; }
  .buttons { align-items: center; display: flex; flex-wrap: wrap; gap: 0.5rem; }
</style>
