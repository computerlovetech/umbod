<script lang="ts">
  import { tick } from 'svelte';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import type { NewFolderState } from '$lib/files/state/new-folder-state.svelte';
  let { state }: { state: NewFolderState } = $props();

  function focusInput(input: HTMLInputElement): void {
    input.focus();
  }

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

<form aria-label="New folder" onsubmit={(event) => { event.preventDefault(); void submit(event.currentTarget); }}>
  <label for="folder-name">Folder name</label>
  <input id="folder-name" name="name" onkeydown={handleEscape} value={state.name} oninput={(event) => state.changeName(event.currentTarget.value)} disabled={state.pending} required autocomplete="off" {@attach focusInput} />
  <label for="folder-description">Description (optional)</label>
  <textarea id="folder-description" aria-describedby="folder-description-hint" value={state.description} oninput={(event) => state.changeDescription(event.currentTarget.value)} disabled={state.pending} onkeydown={handleEscape} rows="3"></textarea>
  <p id="folder-description-hint">What is here, and when should it be read?</p>
  <Button variant="primary" type="submit" onkeydown={handleEscape} disabled={state.pending || state.uncertain || !state.name.trim()}>{state.pending ? 'Creating…' : 'Create folder'}</Button>
  <Button variant="secondary" type="button" onkeydown={handleEscape} disabled={state.pending} onclick={cancel}>Cancel</Button>
  {#if state.error}<p role="alert">{state.error}</p>{/if}
  {#if state.uncertain}<Button variant="secondary" type="button" onkeydown={handleEscape} onclick={state.reload}>Reload folder</Button>{/if}
</form>

<style>
  form { display: flex; flex-wrap: wrap; align-items: center; gap: 0.6rem; margin: 1rem 0; }
  label[for='folder-description'], #folder-description-hint { flex-basis: 100%; }
  #folder-description-hint { margin: 0; color: var(--admin-muted); font-size: 0.9rem; }
  textarea { flex-basis: 100%; resize: vertical; }
  input, textarea { border: 1px solid var(--admin-border); background: var(--admin-panel); color: var(--admin-ink); border-radius: var(--admin-radius); padding: 0.6rem; font: inherit; }
  input { min-width: 0; }
  :focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 2px; }
  [role='alert'] { color: var(--admin-danger); flex-basis: 100%; margin: 0; }
</style>
