<script lang="ts">
  import { tick } from 'svelte';
  import { nativeDialog } from '$lib/components/shared/dialogs/native-dialog';
  import { FileDropState } from '$lib/files/state/file-drop-state.svelte';
  import { formatFileSize, type UploadState } from '$lib/files/state/upload-state.svelte';

  let { state, destination, signIn }: { state: UploadState; destination: string; signIn: () => void } = $props();
  const id = $props.id();
  const drop = new FileDropState((files) => state.select(files), (message) => state.rejectSelection(message), () => state.pending || state.uncertain);

  function choose(input: HTMLInputElement): void {
    state.select(Array.from(input.files ?? []));
    input.value = '';
  }

  function restoreFocus(): void {
    (document.getElementById('upload-file-button') ?? document.getElementById('files-heading'))?.focus();
  }

  function remove(): void {
    state.remove();
    document.getElementById(id + '-file')?.focus();
  }

  async function cancel(): Promise<void> {
    const url = window.location.href;
    state.cancel();
    if (state.open) return;
    await tick();
    if (window.location.href === url) restoreFocus();
  }

  async function submit(form: HTMLFormElement): Promise<void> {
    const url = window.location.href;
    await state.submit();
    if (!form.isConnected && window.location.href === url) restoreFocus();
  }

  async function reloadFolder(): Promise<void> {
    const url = window.location.href;
    await state.reload();
    if (window.location.href === url) document.getElementById('files-heading')?.focus();
  }

</script>

<svelte:window ondragover={drop.preventOutside} ondrop={drop.preventOutside} />

<dialog aria-labelledby={id + '-title'} aria-describedby={id + '-destination'} aria-modal="true" {@attach nativeDialog(() => { void cancel(); }, () => !state.pending, 'input[type="file"]:not(:disabled)')}>
<form id={id + '-form'} aria-label="Upload file" aria-busy={state.pending} onsubmit={(event) => { event.preventDefault(); void submit(event.currentTarget); }}>
  <div class="form-heading">
    <div><h2 id={id + '-title'}>Upload a file</h2><p id={id + '-destination'} class="destination">To <strong>{destination}</strong></p></div>
    <span class="limit">One file · {formatFileSize(state.maxBytes)} maximum</span>
  </div>
  <fieldset disabled={state.pending || state.uncertain}>
    <legend class="visually-hidden">Choose a file to upload</legend>
    <div class={['drop-zone', { 'drag-active': drop.active }]} role="group" aria-label="File drop area" aria-describedby={id + '-hint'} ondragenter={drop.enter} ondragover={drop.over} ondragleave={drop.leave} ondrop={drop.drop}>
      <svg aria-hidden="true" viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6" /></svg>
      <p class="drop-title">{drop.active ? 'Drop your file here' : 'Drag and drop a file here'}</p>
      <div class="file-picker">
        <label for={id + '-file'}>{state.file ? 'Choose a different file' : 'Choose file'}</label>
        <input id={id + '-file'} class="visually-hidden" type="file" aria-describedby={id + '-hint' + (state.file ? ' ' + id + '-selection' : '') + (state.error ? ' ' + id + '-error' : '')} onchange={(event) => choose(event.currentTarget)} />
      </div>
      <p id={id + '-hint'} class="hint">Or use the file picker. Any file type, including empty files. Folders and multiple files are not supported.</p>
    </div>
    {#if state.file}
      <div id={id + '-selection'} class="selection">
        <div class="selected-file"><strong>{state.file.name}</strong><span>{formatFileSize(state.file.size)}</span></div>
        <button type="button" onclick={remove}>Remove file</button>
      </div>
      <div class="name-field">
        <label for={id + '-name'}>File name</label>
        <input id={id + '-name'} value={state.name} oninput={(event) => state.changeName(event.currentTarget.value)} aria-describedby={id + '-name-hint' + (state.error ? ' ' + id + '-error' : '')} required autocomplete="off" />
        <p id={id + '-name-hint'} class="hint">Keep the original name or choose another. Do not use / or \. Existing files are never overwritten.</p>
      </div>
    {/if}
  </fieldset>
  <p class="visually-hidden" role="status" aria-atomic="true">{state.pending ? 'Uploading file…' : state.status}</p>
  {#if state.error}<p id={id + '-error'} class="error" role="alert">{state.error}</p>{/if}
  {#if state.pending}
    <div class="progress"><progress aria-label="Uploading file"></progress><span>Keep this tab open until the upload is confirmed.</span></div>
  {/if}
  <div class="actions">
    <button type="submit" class="primary" disabled={!state.canSubmit}>{state.pending ? 'Uploading…' : 'Upload file'}</button>
    <button type="button" disabled={state.pending} onclick={cancel}>{state.uncertain ? 'Close' : 'Cancel'}</button>
    {#if state.uncertain}<button type="button" onclick={reloadFolder}>Reload folder</button>{/if}
    {#if state.signInRequired}<button type="button" onclick={signIn}>Sign in</button>{/if}
  </div>
</form>
</dialog>

<style>
  dialog { box-sizing: border-box; width: min(42rem, calc(100% - 2rem)); max-width: none; max-height: calc(100dvh - 2rem); overflow: auto; padding: 0; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-panel); color: var(--admin-ink); box-shadow: var(--admin-shadow-dialog); }
  dialog::backdrop { background: var(--admin-overlay); }
  form { padding: 1.25rem; margin: 0; }
  .form-heading { display: flex; flex-wrap: wrap; align-items: start; justify-content: space-between; gap: 0.75rem; margin-bottom: 1rem; }
  h2 { font-size: 1.05rem; margin: 0 0 0.35rem; }
  p { margin: 0; }
  .destination, .limit, .hint, .selected-file span, .progress { font-size: 0.85rem; color: var(--admin-muted); }
  .destination { overflow-wrap: anywhere; }
  fieldset { min-width: 0; border: 0; padding: 0; margin: 0; }
  .drop-zone { display: flex; flex-direction: column; align-items: center; gap: 0.8rem; padding: 1.75rem 1rem; border: 2px dashed var(--admin-border); border-radius: var(--admin-radius); text-align: center; }
  .drag-active { border-color: var(--admin-accent); background: color-mix(in srgb, var(--admin-accent) 8%, var(--admin-panel)); }
  .drop-zone svg { color: var(--admin-accent); }
  .drop-title { font-weight: 500; }
  .file-picker { position: relative; border-radius: var(--admin-radius); }
  .file-picker label { display: block; padding: 0.6rem 0.9rem; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); cursor: pointer; }
  .file-picker:focus-within { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
  fieldset:disabled .file-picker label { cursor: default; opacity: 0.6; }
  .hint { line-height: 1.5; }
  .selection { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 1rem 0; }
  .selected-file { display: flex; flex-direction: column; gap: 0.3rem; min-width: 0; overflow-wrap: anywhere; }
  .name-field { display: grid; gap: 0.5rem; }
  .name-field label { font-size: 0.9rem; font-weight: 500; }
  input:not([type='file']), button { border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-panel); color: var(--admin-ink); font: inherit; padding: 0.6rem 0.9rem; min-width: 0; }
  button { cursor: pointer; }
  button:disabled { opacity: 0.6; cursor: default; }
  .primary { background: var(--admin-accent); color: var(--admin-panel); border-color: var(--admin-accent); }
  .actions { display: flex; flex-wrap: wrap; gap: 0.6rem; margin-top: 1rem; }
  .error { color: var(--admin-danger); margin-top: 1rem; line-height: 1.5; }
  .progress { display: flex; flex-direction: column; gap: 0.5rem; margin-top: 1rem; }
  progress { width: 100%; accent-color: var(--admin-accent); }
  :focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
  .visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
  @media (max-width: 480px) { form { padding: 1rem; } .selection { flex-wrap: wrap; } }
</style>
