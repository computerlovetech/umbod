<script lang="ts">
  import Button from '$lib/components/admin/shared/Button.svelte';
  import FileTypeIcon from './FileTypeIcon.svelte';
  import { FileThumbnailState } from './file-thumbnail-state.svelte';
  import { tick } from 'svelte';
  import ModalShell from '$lib/components/shared/ModalShell.svelte';
  import { FileDropState } from '$lib/files/state/file-drop-state.svelte';
  import { formatFileSize, type UploadState } from '$lib/files/state/upload-state.svelte';

  let { state, destination, signIn }: { state: UploadState; destination: string; signIn: () => void } = $props();
  const id = $props.id();
  const thumbnail = new FileThumbnailState(() => state.file);
  const drop = new FileDropState((files) => state.select(files), (message) => state.rejectSelection(message), () => state.pending || state.uncertain);

  function choose(input: HTMLInputElement): void {
    state.select(Array.from(input.files ?? []));
    input.value = '';
  }

  function restoreFocus(): void {
    (document.getElementById('upload-file-button') ?? document.getElementById('files-heading'))?.focus();
  }

  async function remove(): Promise<void> {
    state.remove();
    await tick();
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

<ModalShell title="Upload a file" titleId={id + '-title'} descriptionId={id + '-destination'} close={() => { void cancel(); }} closeDisabled={state.pending} initialFocus={'input[type="file"]:not(:disabled)'} --modal-width="42rem" --modal-padding="1.25rem" --modal-overflow="auto">
<form id={id + '-form'} aria-label="Upload file" aria-busy={state.pending} onsubmit={(event) => { event.preventDefault(); void submit(event.currentTarget); }}>
  <div class="form-heading">
    <p id={id + '-destination'} class="destination">To <strong>{destination}</strong></p>
    <span class="limit">One file at a time</span>
  </div>
  <fieldset disabled={state.pending || state.uncertain}>
    <legend class="visually-hidden">Choose a file to upload</legend>
    <div class={['drop-zone', { 'has-selection': !!state.file, 'drag-active': drop.active }]} role="group" aria-label="File drop area" aria-describedby={id + '-hint'} ondragenter={drop.enter} ondragover={drop.over} ondragleave={drop.leave} ondrop={drop.drop}>
      {#if state.file}
        <div class="selection-heading">
          <span class="selected-badge"><svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9" /><path d="m8 12 3 3 5-6" /></svg>File selected</span>
          <Button variant="quiet" size="compact" iconOnly type="button" aria-label="Remove file" onclick={remove}><svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7"><path d="m7 7 10 10M17 7 7 17" /></svg></Button>
        </div>
        <div id={id + '-selection'} class="selection">
          <div class="thumbnail">
            {#key state.file}
              {#if thumbnail.visible}
                <img {@attach thumbnail.attach} alt="Selected file preview" />
              {:else}
                <FileTypeIcon kind="file" name={state.file.name} contentType={state.file.type} size={32} />
              {/if}
            {/key}
          </div>
          <div class="selected-file"><strong>{state.file.name}</strong><span>{formatFileSize(state.file.size)}</span></div>
        </div>
      {:else}
        <svg aria-hidden="true" viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6" /></svg>
        <p class="drop-title">{drop.active ? 'Drop your file here' : 'Drag and drop a file here'}</p>
      {/if}
      <div class="file-picker">
        <label for={id + '-file'}>{#if state.file}<svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 8h15m-4-4 4 4-4 4M20 16H5m4-4-4 4 4 4" /></svg>{/if}{state.file ? 'Change file' : 'Choose file'}</label>
        <input id={id + '-file'} class="visually-hidden" type="file" aria-describedby={id + '-hint' + (state.file ? ' ' + id + '-selection' : '') + (state.error ? ' ' + id + '-error' : '')} onchange={(event) => choose(event.currentTarget)} />
      </div>
      <p id={id + '-hint'} class={['hint', { 'visually-hidden': !!state.file }]}>Or use the file picker. Any file type, including empty files. Folders and multiple files are not supported.</p>
    </div>
    {#if state.file}
      <div class="name-field">
        <label for={id + '-name'}>File name</label>
        <input id={id + '-name'} value={state.name} oninput={(event) => state.changeName(event.currentTarget.value)} aria-describedby={id + '-name-hint' + (state.error ? ' ' + id + '-error' : '')} required autocomplete="off" />
        <p id={id + '-name-hint'} class="hint">Keep the original name or choose another. Do not use / or \. Existing files are never overwritten.</p>
      </div>
    {/if}
    <div class="name-field">
      <label for={id + '-description'}>Description (optional)</label>
      <textarea id={id + '-description'} aria-describedby={id + '-description-hint'} value={state.description} oninput={(event) => state.changeDescription(event.currentTarget.value)} rows="3"></textarea>
      <p id={id + '-description-hint'} class="hint">What is here, and when should it be read?</p>
    </div>
  </fieldset>
  <p class="visually-hidden" role="status" aria-atomic="true">{state.pending ? 'Uploading file…' : state.status}</p>
  {#if state.error}<p id={id + '-error'} class="error" role="alert">{state.error}</p>{/if}
  {#if state.pending}
    <div class="progress"><progress aria-label="Uploading file"></progress><span>Keep this tab open until the upload is confirmed.</span></div>
  {/if}
  <div class="actions">
    <Button variant="primary" type="submit" disabled={!state.canSubmit}>{state.pending ? 'Uploading…' : 'Upload file'}</Button>
    <Button variant="secondary" type="button" disabled={state.pending} onclick={cancel}>{state.uncertain ? 'Close' : 'Cancel'}</Button>
    {#if state.uncertain}<Button variant="secondary" type="button" onclick={reloadFolder}>Reload folder</Button>{/if}
    {#if state.signInRequired}<Button variant="secondary" type="button" onclick={signIn}>Sign in</Button>{/if}
  </div>
</form>
</ModalShell>

<style>
  form { margin: 1rem 0 0; }
  .form-heading { display: flex; flex-wrap: wrap; align-items: start; justify-content: space-between; gap: 0.75rem; margin-bottom: 1rem; }
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
  .has-selection { align-items: stretch; gap: 1rem; padding: 1.25rem; border: 1px solid var(--admin-accent-border); background: var(--admin-accent-soft); text-align: left; }
  .selection-heading { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
  .selected-badge { display: inline-flex; align-items: center; gap: 0.4rem; color: var(--admin-accent); font-size: 0.8rem; font-weight: 600; }
  .selection { display: flex; align-items: center; gap: 1rem; min-width: 0; }
  .thumbnail { display: grid; place-items: center; flex-shrink: 0; width: 5rem; height: 5rem; overflow: hidden; border: 1px solid var(--admin-accent-border); border-radius: var(--admin-radius); background: var(--admin-panel); color: var(--admin-accent); }
  .thumbnail img { width: 100%; height: 100%; object-fit: cover; }
  .has-selection .file-picker { display: flex; justify-content: flex-end; border-top: 1px solid var(--admin-accent-border); border-radius: 0; padding-top: 0.8rem; }
  .has-selection .file-picker label { display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.2rem; border: 0; color: var(--admin-accent); font-size: 0.85rem; font-weight: 600; }
  .has-selection.drag-active { border-color: var(--admin-accent); outline: 2px solid var(--admin-accent); outline-offset: 3px; }
  .selected-file { display: flex; flex-direction: column; gap: 0.3rem; min-width: 0; overflow-wrap: anywhere; }
  .name-field { display: grid; gap: 0.5rem; margin-top: 1rem; }
  .name-field label { font-size: 0.9rem; font-weight: 500; }
  textarea { resize: vertical; }
  input:not([type='file']), textarea { border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-panel); color: var(--admin-ink); font: inherit; padding: 0.6rem 0.9rem; min-width: 0; }
  .actions { display: flex; flex-wrap: wrap; gap: 0.6rem; margin-top: 1rem; }
  .error { color: var(--admin-danger); margin-top: 1rem; line-height: 1.5; }
  .progress { display: flex; flex-direction: column; gap: 0.5rem; margin-top: 1rem; }
  progress { width: 100%; accent-color: var(--admin-accent); }
  :focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
  .visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
  @media (max-width: 480px) { .has-selection { padding: 1rem; } .thumbnail { width: 4rem; height: 4rem; } }
</style>
