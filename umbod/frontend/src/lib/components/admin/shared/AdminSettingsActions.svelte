<script lang="ts">
  import Button from './Button.svelte';

  let { busy, dirty, conflict = false, saveDisabled = false, onDiscard, onSave }: {
    busy: boolean;
    dirty: boolean;
    conflict?: boolean;
    saveDisabled?: boolean;
    onDiscard: () => void;
    onSave: () => Promise<void>;
  } = $props();
</script>

<div class="actions">
  <p role="status">{busy ? 'Saving changes…' : dirty || conflict ? 'Unsaved changes' : 'No unsaved changes'}</p>
  <div class="buttons">
    {#if dirty || conflict}
      <Button variant="secondary" disabled={busy} onclick={onDiscard}>Discard changes</Button>
    {/if}
    <Button disabled={busy || !dirty || conflict || saveDisabled} onclick={onSave}>Save changes</Button>
  </div>
</div>

<style>
  .actions { align-items: center; display: flex; flex-wrap: wrap; gap: 1rem; justify-content: space-between; margin-top: 1rem; }
  p { color: var(--admin-muted); font-size: 13px; line-height: 1.5; margin: 0; }
  .buttons { align-items: center; display: flex; flex-wrap: wrap; gap: 0.5rem; }
</style>
