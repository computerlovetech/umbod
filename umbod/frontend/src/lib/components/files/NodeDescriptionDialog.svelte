<script lang="ts">
  import Button from '$lib/components/admin/shared/Button.svelte';
  import { nativeDialog } from '$lib/components/shared/dialogs/native-dialog';
  import type { DescriptionState } from '$lib/files/state/description-state.svelte';
  let { state, name }: { state: DescriptionState; name: string } = $props();
  const id = $props.id();
</script>

<dialog aria-labelledby={id + '-title'} {@attach nativeDialog(state.cancel, () => !state.pending, 'textarea')}>
  <h2 id={id + '-title'}>Edit description</h2>
  <p>{name || 'Files'}</p>
  <form aria-label="Edit description" aria-busy={state.pending} onsubmit={(event) => { event.preventDefault(); void state.save(); }}>
    <label for={id + '-description'}>Description</label>
    <p id={id + '-hint'}>What is here, and when should it be read?</p>
    <textarea id={id + '-description'} aria-describedby={id + '-hint'} value={state.draft} oninput={(event) => state.change(event.currentTarget.value)} disabled={state.pending || state.needsReload} rows="4"></textarea>
    {#if state.error}<p role="alert">{state.error}</p>{/if}
    {#if state.needsReload}<Button variant="secondary" type="button" onclick={state.reload} disabled={state.pending}>Reload item</Button>{/if}
    <div class="actions">
      <Button variant="secondary" type="button" onclick={state.cancel} disabled={state.pending}>Cancel</Button>
      <Button variant="primary" type="submit" disabled={!state.canSave}>{state.pending ? 'Saving…' : 'Save description'}</Button>
    </div>
  </form>
  <p role="status" aria-atomic="true">{state.pending ? 'Saving description…' : state.status}</p>
</dialog>

<style>
  dialog { box-sizing: border-box; width: min(36rem, calc(100% - 2rem)); max-height: calc(100dvh - 2rem); overflow: auto; padding: 1.5rem; background: var(--admin-panel); color: var(--admin-ink); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); box-shadow: var(--admin-shadow-dialog); }
  dialog::backdrop { background: var(--admin-overlay); }
  h2, p { overflow-wrap: anywhere; }
  p { color: var(--admin-muted); }
  label { display: block; margin-block: 1rem 0.4rem; }
  textarea { display: block; box-sizing: border-box; width: 100%; margin-bottom: 0.6rem; resize: vertical; }
  textarea { border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-panel); color: var(--admin-ink); font: inherit; padding: 0.6rem; }
  .actions { display: flex; justify-content: flex-end; gap: 0.6rem; margin-top: 1rem; }
  [role='alert'] { color: var(--admin-danger); }
  :focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
</style>
