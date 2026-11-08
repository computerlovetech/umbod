<script lang="ts">
  import { tick } from 'svelte';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import ModalShell from '$lib/components/shared/ModalShell.svelte';
  import type { NewFolderState } from '$lib/files/state/new-folder-state.svelte';
  let { state }: { state: NewFolderState } = $props();

  async function submit(form: HTMLFormElement): Promise<void> {
    const trigger = document.getElementById('new-folder-button');
    await state.submit();
    if (form.isConnected) form.querySelector<HTMLInputElement>('input')?.focus();
    else if (trigger?.isConnected) trigger.focus();
  }

  function handleEscape(event: KeyboardEvent): void {
    if (event.key !== 'Escape') return;
    event.preventDefault();
    void cancel();
  }

  async function cancel(): Promise<void> {
    state.cancel();
    if (state.open) return;
    await tick();
    document.getElementById('new-folder-button')?.focus();
  }
</script>

<ModalShell title="New folder" titleId="new-folder-title" close={cancel} initialFocus="#folder-name">
<form aria-label="New folder" aria-busy={state.pending} onsubmit={(event) => { event.preventDefault(); void submit(event.currentTarget); }}>
  <label for="folder-name">Folder name</label>
  <input id="folder-name" name="name" onkeydown={handleEscape} value={state.name} oninput={(event) => state.changeName(event.currentTarget.value)} disabled={state.pending} required autocomplete="off" />
  <label for="folder-description">Description (optional)</label>
  <textarea id="folder-description" aria-describedby="folder-description-hint" value={state.description} oninput={(event) => state.changeDescription(event.currentTarget.value)} disabled={state.pending} onkeydown={handleEscape} rows="3"></textarea>
  <p id="folder-description-hint">What is here, and when should it be read?</p>
  <div class="actions">
    <Button variant="secondary" type="button" onkeydown={handleEscape} disabled={state.pending} onclick={cancel}>Cancel</Button>
    <Button variant="primary" type="submit" onkeydown={handleEscape} disabled={state.pending || state.uncertain || !state.name.trim()}>{state.pending ? 'Creating…' : 'Create folder'}</Button>
  </div>
  {#if state.error}<p role="alert">{state.error}</p>{/if}
  {#if state.uncertain}<Button variant="secondary" type="button" onkeydown={handleEscape} onclick={state.reload}>Reload folder</Button>{/if}
</form>
</ModalShell>

<style>
  form { display: flex; flex-direction: column; gap: 0.6rem; padding-top: 1rem; overflow: auto; }
  .actions { display: flex; justify-content: flex-end; gap: 0.6rem; margin-top: 0.4rem; }
  #folder-description-hint { margin: 0; color: var(--admin-muted); font-size: 0.9rem; }
  textarea { resize: vertical; }
  input, textarea { border: 1px solid var(--admin-border); background: var(--admin-panel); color: var(--admin-ink); border-radius: var(--admin-radius); padding: 0.6rem; font: inherit; }
  input { min-width: 0; }
  :focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 2px; }
  [role='alert'] { color: var(--admin-danger); flex-basis: 100%; margin: 0; }
</style>
