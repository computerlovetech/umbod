<script lang="ts">
  import { filesHref, type FilesState } from '$lib/files/state/files-state.svelte';
  import type { NewFolderState } from '$lib/files/state/new-folder-state.svelte';
  import type { UploadState } from '$lib/files/state/upload-state.svelte';
  import { FileDropState } from '$lib/files/state/file-drop-state.svelte';
  import NodeShareButton from './NodeShareButton.svelte';
  import NodeSharingDialog from './NodeSharingDialog.svelte';
  import FilesNavigation from './FilesNavigation.svelte';
  import FileDeletionDialog from './FileDeletionDialog.svelte';
  import FileUploadForm from './FileUploadForm.svelte';
  import NewFolderForm from './NewFolderForm.svelte';

  let { state, folder, upload, signIn }: { state: FilesState; folder: NewFolderState; upload: UploadState; signIn: () => void } = $props();

  const pageDrop = new FileDropState((files) => { void upload.drop(files); }, (message) => upload.rejectDrop(message), () => !upload.canDrop);

  function enterWindow(event: DragEvent): void {
    if (!event.defaultPrevented) pageDrop.enter(event);
  }

  function overWindow(event: DragEvent): void {
    if (!event.defaultPrevented) pageDrop.over(event);
  }

  function leaveWindow(event: DragEvent): void {
    if (event.relatedTarget === null && (event.clientX <= 0 || event.clientY <= 0 || event.clientX >= window.innerWidth || event.clientY >= window.innerHeight)) pageDrop.reset();
    else pageDrop.leave();
  }

  function dropWindow(event: DragEvent): void {
    if (!event.defaultPrevented) pageDrop.drop(event);
  }

  function cancelDrag(event: KeyboardEvent): void {
    if (event.key === 'Escape') pageDrop.reset();
  }

  function updatedAt(timestamp: string): string {
    return new Date(timestamp).toLocaleString();
  }
</script>

<svelte:window ondragenter={enterWindow} ondragover={overWindow} ondragleave={leaveWindow} ondrop={dropWindow} onblur={pageDrop.reset} onkeydown={cancelDrag} />

{#if pageDrop.active && upload.canDrop}
  <div class="page-file-drop" role="status" aria-atomic="true">
    <div class="drop-prompt">
      <svg aria-hidden="true" viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6" /></svg>
      <h2>Drop a file to upload</h2>
      <p>To {state.node?.name || 'Files'}</p>
      <p>One file at a time. Upload starts when you drop.</p>
    </div>
  </div>
{/if}

<div class="heading">
  <h1 id="files-heading" class="admin-title" tabindex="-1" {@attach state.rowDeletion.attachFocus}>{state.node?.name || 'Files'}</h1>
  {#if state.node?.kind === 'directory'}
    <div class="toolbar">
      <NodeShareButton node={state.node} sharing={state.sharing} />
      {#if state.phase === 'ready'}
      {#if upload.available}<button id="upload-file-button" onclick={upload.show} disabled={upload.open}>Upload file</button>{/if}
      <button id="new-folder-button" onclick={folder.show} disabled={folder.open}>New folder</button>
      {/if}
    </div>
  {/if}
</div>
{#if state.node}<FilesNavigation state={state.navigation} {signIn} />{/if}
<p class="upload-status" role="status" aria-atomic="true">{upload.pending ? 'Uploading file…' : upload.status}</p>

{#if state.mutationNotice}<p role="status">{state.mutationNotice}</p>{/if}

{#if state.phase === 'loading'}
  <p role="status">Loading files…</p>
{:else if state.phase !== 'ready'}
  <p role="alert">{state.phase === 'denied' ? "You don't have access to this location." : state.phase === 'sign-in' ? 'Sign in to view files.' : state.phase === 'missing' ? 'This location is unavailable.' : "Couldn't load files."}</p>
  {#if state.phase === 'sign-in'}
    <button onclick={signIn}>Sign in</button>
  {:else}
    <button onclick={folder.reload}>Retry</button>
  {/if}
{:else if state.node}
  {#if state.node.kind === 'directory'}
    {#if !upload.available && upload.error}<p role="alert">{upload.error}</p>{/if}
    {#if state.uploadAvailability === 'error'}
      <p class="availability-error">Couldn't check upload availability. <button onclick={state.checkUploadAvailability}>Retry upload check</button></p>
    {:else if state.uploadAvailability === 'sign-in'}
      <p class="availability-error">Sign in to check upload availability. <button onclick={signIn}>Sign in</button></p>
    {/if}
    {#if upload.open && upload.available}<FileUploadForm state={upload} destination={state.node.name || 'Files'} {signIn} />{/if}
    {#if folder.open}<NewFolderForm state={folder} />{/if}
    {#if state.children.length === 0}
      <p role="status">This folder is empty.</p>
    {:else}
      <div class="items">
        <table>
          <caption class="visually-hidden">Files and folders</caption>
          <thead><tr><th scope="col">Name</th><th scope="col">Type</th><th scope="col">Updated</th><th scope="col" class="row-actions">Actions</th></tr></thead>
          <tbody>
            {#each state.children as item (item.id)}
              {@const deletion = state.rowDeletion.controllers.get(item.id)}
              <tr class="item-row">
                <td>
                  <a class="item-name" href={filesHref(item.id)}>
                    <svg role="img" aria-label={item.kind === 'directory' ? 'Folder' : 'File'} viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5">
                      {#if item.kind === 'directory'}<path d="M3 6h7l2 3h9v11H3z" />{:else}<path d="M6 3h8l4 4v14H6z M14 3v5h4" />{/if}
                    </svg>
                    {item.name}
                  </a>
                </td>
                <td>{item.kind === 'directory' ? 'Folder' : 'File'}</td>
                <td><time datetime={item.updated_at}>{updatedAt(item.updated_at)}</time></td>
                <td class="row-actions">
                  <NodeShareButton node={item} sharing={state.sharing} compact />
                  {#if item.kind === 'file' && deletion}
                    {#if deletion.available || deletion.pending}
                      <button type="button" class="row-delete" {@attach state.rowDeletion.attachButton(item.id)} aria-label={`Delete “${item.name}”`} title={deletion.pending ? 'Deleting…' : `Delete “${item.name}”`} aria-busy={deletion.pending} onclick={deletion.show} disabled={deletion.pending || !!deletion.confirmation}>
                        <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M9 6V4h6v2M5 6l1 14h12l1-14M10 10v6M14 10v6" /></svg>
                      </button>
                      {#if deletion.pending}<span class="visually-hidden" role="status">Deleting “{item.name}”…</span>{/if}
                    {/if}
                    {#if deletion.confirmation}<FileDeletionDialog state={deletion} onconfirm={() => { void state.rowDeletion.confirm(item.id); }} oncancel={() => { void state.rowDeletion.cancel(item.id); }} />{/if}
                    {#if deletion.message}<p role="alert">{deletion.message}</p>{/if}
                    {#if deletion.needsReload}<button {@attach state.rowDeletion.attachRecovery(item.id)} onclick={deletion.reconcile} disabled={deletion.pending}>Reload folder</button>{/if}
                    {#if deletion.signInRequired}<button onclick={signIn}>Sign in</button>{/if}
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  {:else}
    <section aria-label="File details" class="details">
      <NodeShareButton node={state.node} sharing={state.sharing} />
      {#if state.deletion.available}<button onclick={state.deletion.show} disabled={state.deletion.pending || !!state.deletion.confirmation}>Delete file</button>{/if}
      {#if state.deletion.confirmation}<FileDeletionDialog state={state.deletion} />{/if}
      {#if state.deletion.pending}<p role="status">Deleting file…</p>{/if}
      {#if state.deletion.message}<p role="alert">{state.deletion.message}</p>{/if}
      {#if state.deletion.needsReload}<button onclick={state.deletion.reconcile}>{state.deletion.mutationSucceeded ? 'Reload parent folder' : 'Reload file'}</button>{/if}
      {#if state.deletion.signInRequired}<button onclick={signIn}>Sign in</button>{/if}
      <dl>
        <dt>Type</dt><dd>File</dd>
        <dt>Content type</dt><dd>{typeof state.node.metadata.content_type === 'string' ? state.node.metadata.content_type : 'Not specified'}</dd>
        <dt>Updated</dt><dd><time datetime={state.node.updated_at}>{updatedAt(state.node.updated_at)}</time></dd>
        {#each Object.entries(state.node.metadata.attributes) as [name, value] (name)}
          <dt>{name}</dt><dd>{value}</dd>
        {/each}
      </dl>
    </section>
  {/if}
{/if}

{#if state.sharing.dialog.open}<NodeSharingDialog state={state.sharing.dialog} {signIn} />{/if}
<p role="status" aria-atomic="true">{state.sharing.dialog.status}</p>

<style>
  .page-file-drop { position: fixed; inset: 0; z-index: 1000; display: grid; place-items: center; padding: 1rem; background: rgb(30 35 33 / 65%); pointer-events: none; }
  .drop-prompt { box-sizing: border-box; width: min(100%, 32rem); padding: 2.5rem 1.5rem; border: 2px dashed var(--admin-accent); border-radius: var(--admin-radius); background: var(--admin-panel); text-align: center; color: var(--admin-ink); overflow-wrap: anywhere; }
  .drop-prompt svg { color: var(--admin-accent); }
  .drop-prompt p { line-height: 1.5; }
  .heading { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 1rem; }
  .toolbar { display: flex; flex-wrap: wrap; gap: 0.6rem; }
  .upload-status:empty { margin: 0; }
  .upload-status:not(:empty) { color: var(--admin-ink); }
  .availability-error { font-size: 0.9rem; }
  h1 { min-width: 0; overflow-wrap: anywhere; }
  a { color: var(--admin-accent); overflow-wrap: anywhere; }
  button { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); color: var(--admin-ink); font: inherit; cursor: pointer; padding: 0.6rem 0.9rem; }
  button:disabled { opacity: 0.6; cursor: default; }
  :focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
  .items { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.9rem; }
  th, td { padding: 0.8rem 0.6rem; border-bottom: 1px solid var(--admin-border); }
  th { color: var(--admin-muted); font-weight: 500; }
  .item-row { position: relative; }
  .item-row:hover, .item-row:focus-within { background: var(--admin-soft); }
  .row-actions { text-align: right; }
  .row-actions > button { position: relative; z-index: 1; }
  .row-delete { display: inline-flex; align-items: center; justify-content: center; width: 2.75rem; height: 2.75rem; padding: 0; border: 0; background: transparent; color: var(--admin-danger); }
  .row-delete:hover:not(:disabled) { background: color-mix(in srgb, var(--admin-danger) 8%, transparent); }
  .item-name { display: flex; align-items: center; gap: 0.6rem; }
  .item-name::after { content: ''; position: absolute; inset: 0; cursor: pointer; }
  svg { flex-shrink: 0; }
  p, dt { color: var(--admin-muted); }
  [role='alert'] { color: var(--admin-danger); }
  .drop-prompt h2 { font-size: 1.15rem; overflow-wrap: anywhere; }
  dl { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 0.65rem 1rem; font-size: 0.9rem; }
  dd { margin: 0; overflow-wrap: anywhere; }
  .details { border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: 1rem; }
  .visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
</style>
