<script lang="ts">
  import Button from '$lib/components/admin/shared/Button.svelte';
  import { filesHref, type FilesState } from '$lib/files/state/files-state.svelte';
  import type { NewFolderState } from '$lib/files/state/new-folder-state.svelte';
  import type { UploadState } from '$lib/files/state/upload-state.svelte';
  import { FileDropState } from '$lib/files/state/file-drop-state.svelte';
  import PermissionBadge from './PermissionBadge.svelte';
  import NodeActions from './NodeActions.svelte';
  import NodeShareButton from './NodeShareButton.svelte';
  import NodeSharingDialog from './NodeSharingDialog.svelte';
  import FilesNavigation from './FilesNavigation.svelte';
  import FileDeletionDialog from './FileDeletionDialog.svelte';
  import FileUploadForm from './FileUploadForm.svelte';
  import FilesDescription from './FilesDescription.svelte';
  import FilesContainer from './FilesContainer.svelte';
  import FileTypeIcon from './FileTypeIcon.svelte';
  import NewFolderForm from './NewFolderForm.svelte';

  let { state, folder, upload, signIn }: { state: FilesState; folder: NewFolderState; upload: UploadState; signIn: () => void } = $props();

  const pageDrop = new FileDropState((files) => { void upload.drop(files); }, (message) => upload.rejectDrop(message), () => !upload.canDrop);

  function enterWindow(event: DragEvent): void {
    if (!event.defaultPrevented) pageDrop.enter(event);
  }

  function overWindow(event: DragEvent): void {
    state.dragMove.followPointer(event);
    state.dragMove.preventOutside(event);
    if (!event.defaultPrevented) pageDrop.over(event);
  }

  function leaveWindow(event: DragEvent): void {
    if (event.relatedTarget === null && (event.clientX <= 0 || event.clientY <= 0 || event.clientX >= window.innerWidth || event.clientY >= window.innerHeight)) pageDrop.reset();
    else pageDrop.leave();
  }

  function dropWindow(event: DragEvent): void {
    state.dragMove.preventOutside(event);
    if (!event.defaultPrevented) pageDrop.drop(event);
  }

  function resetDrag(): void {
    pageDrop.reset();
    state.dragMove.cancel();
  }

  function cancelDrag(event: KeyboardEvent): void {
    if (event.key === 'Escape') resetDrag();
  }

  function updatedAt(timestamp: string): string {
    return new Date(timestamp).toLocaleString();
  }
</script>

<svelte:window ondragenter={enterWindow} ondragover={overWindow} ondragleave={leaveWindow} ondrop={dropWindow} onblur={resetDrag} ondrag={state.dragMove.followPointer} ondragend={state.dragMove.cancel} onkeydown={cancelDrag} />

<img class="file-drag-image" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" alt="" aria-hidden="true" width="1" height="1" draggable="false" decoding="sync" {@attach state.dragMove.attachDragImage} />
{#if state.dragMove.dragging}
  <div class="file-drag-preview" aria-hidden="true" style:--preview-x={`${state.dragMove.previewX}px`} style:--preview-y={`${state.dragMove.previewY}px`}>
    <FileTypeIcon kind="file" name={state.dragMove.previewName} size={28} />
    <div class="file-drag-label"><span>Move file</span><strong>{state.dragMove.previewName}</strong></div>
  </div>
{/if}

{#if pageDrop.active && upload.canDrop}
  <div class="page-file-drop" role="status" aria-atomic="true">
    <div class="drop-prompt">
      <svg aria-hidden="true" viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6" /></svg>
      <h2>Drop a file to upload</h2>
      <p>To {state.locationName}</p>
      <p>One file at a time. Upload starts when you drop.</p>
    </div>
  </div>
{/if}

<FilesContainer>
  {#snippet identity()}
    <div class="node-identity">
      <h1 id="files-heading" class="admin-title" tabindex="-1" {@attach state.rowDeletion.attachFocus}>{state.locationName}</h1>
      {#if state.phase === 'ready' && state.node}<PermissionBadge permissions={state.node.permissions} />{/if}
    </div>
    {#if state.phase === 'ready' && state.node}<NodeActions update={state.update} description={state.description} name={state.locationName} displayName={state.atPersonalRoot ? state.locationName : undefined} node={state.node} mutationsAllowed={!state.atPersonalRoot} {signIn} />{/if}
  {/snippet}
  {#snippet navigation()}
    {#if state.node}<FilesNavigation state={state.navigation} {signIn} />{/if}
  {/snippet}
  {#snippet sharing()}
    {#if state.phase === 'ready' && state.node}<NodeShareButton node={state.node} sharing={state.sharing} />{/if}
  {/snippet}
  {#snippet actions()}
    {#if state.phase === 'ready' && state.node?.kind === 'directory'}
      {#if upload.available}<Button variant="primary" id="upload-file-button" onclick={upload.show} disabled={upload.open}>Upload file</Button>{/if}
      {#if state.createDirectoryAllowed}<Button variant="primary" id="new-folder-button" onclick={folder.show} disabled={folder.open}>New folder</Button>{/if}
    {:else if state.phase === 'ready' && state.node?.kind === 'file' && state.deletion.available}
      <Button variant="danger" onclick={state.deletion.show} disabled={state.deletion.pending || !!state.deletion.confirmation}>Delete file</Button>
    {/if}
  {/snippet}
  {#snippet description()}
    {#if state.phase === 'ready' && state.node}<FilesDescription state={state.description} />{/if}
  {/snippet}
  {#snippet children()}
<p class="upload-status" role="status" aria-atomic="true">{upload.pending ? 'Uploading file…' : upload.status}</p>

{#if state.mutationNotice}<p role="status">{state.mutationNotice}</p>{/if}
<p class="drag-status" role="status" aria-atomic="true">{state.dragMove.status}</p>
{#if state.dragMove.error}<p role="alert">{state.dragMove.error}</p>{/if}
{#if state.dragMove.needsReload}<Button variant="secondary" onclick={state.dragMove.reload} disabled={state.dragMove.pending}>Reload folder</Button>{/if}

{#if state.phase === 'loading'}
  <p role="status">Loading files…</p>
{:else if state.phase !== 'ready'}
  <p role="alert">{state.phase === 'denied' ? "You don't have access to this location." : state.phase === 'sign-in' ? 'Sign in to view files.' : state.phase === 'missing' ? 'This location is unavailable.' : "Couldn't load files."}</p>
  {#if state.phase === 'sign-in'}
    <Button variant="secondary" onclick={signIn}>Sign in</Button>
  {:else}
    <Button variant="secondary" onclick={folder.reload}>Retry</Button>
  {/if}
{:else if state.node}
  {#if state.node.kind === 'directory'}
    {#if !upload.available && upload.error}<p role="alert">{upload.error}</p>{/if}
    {#if state.uploadAvailability === 'sign-in'}
      <p class="availability-error">Sign in to check upload availability. <Button variant="quiet" size="compact" onclick={signIn}>Sign in</Button></p>
    {/if}
    {#if upload.open && upload.available}<FileUploadForm state={upload} destination={state.locationName} {signIn} />{/if}
    {#if folder.open}<NewFolderForm state={folder} />{/if}
    {#if state.children.length === 0}
      <p role="status">This folder is empty.</p>
    {:else}
      <div class="items">
        <table>
          <caption class="visually-hidden">Files and folders</caption>
          <colgroup><col /><col class="type-column" /><col class="updated-column" /><col class="actions-column" /></colgroup>
          <thead><tr><th scope="col">Name</th><th scope="col">Type</th><th scope="col">Updated</th><th scope="col" class="row-actions">Actions</th></tr></thead>
          <tbody>
            {#each state.children as item (item.id)}
              {@const deletion = state.rowDeletion.controllers.get(item.id)}
              {@const editing = state.rowEditing.controllers.get(item.id)}
              {@const presentation = state.nodePresentation(item)}
              <tr class={['item-row', presentation.isHome && 'home-row', state.dragMove.isSource(item.id) && 'drag-source', state.dragMove.isTarget(item.id) && 'drop-target']} draggable={state.dragMove.canDrag(item.id)} {@attach state.dragMove.attachRow(item.id)} ondragstart={(event) => state.dragMove.start(item.id, event)} ondragover={(event) => state.dragMove.over(item.id, event)} ondragleave={(event) => state.dragMove.leave(item.id, event)} ondrop={(event) => state.dragMove.drop(item.id, event)}>
                <td>
                  <div class="row-name"><a class="item-name" href={filesHref(item.id)} title={presentation.name} draggable="false">
                    <FileTypeIcon kind={presentation.iconKind} name={presentation.name} contentType={item.metadata.content_type} />
                    <span class="item-name-label">{presentation.name}</span>
                  </a><PermissionBadge permissions={item.permissions} /></div>
                </td>
                <td>{item.kind === 'directory' ? 'Folder' : 'File'}</td>
                <td><time datetime={item.updated_at}>{updatedAt(item.updated_at)}</time></td>
                <td class="row-actions">
                  {#if editing}<NodeActions update={editing.update} description={editing.description} name={presentation.name} displayName={presentation.isHome ? presentation.name : undefined} node={item} sharing={state.sharing} {deletion} onconfirm={() => { void state.rowDeletion.confirm(item.id); }} {signIn} />{/if}
                  {#if item.kind === 'file' && deletion}
                    {#if deletion.pending}<span class="visually-hidden" role="status">Deleting “{item.name}”…</span>{/if}
                    {#if deletion.message}<p role="alert">{deletion.message}</p>{/if}
                    {#if deletion.needsReload}<Button variant="secondary" {@attach state.rowDeletion.attachRecovery(item.id)} onclick={deletion.reconcile} disabled={deletion.pending}>Reload folder</Button>{/if}
                    {#if deletion.signInRequired}<Button variant="secondary" onclick={signIn}>Sign in</Button>{/if}
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  {:else}
    <section aria-label="File details">
      {#if state.deletion.confirmation}<FileDeletionDialog state={state.deletion} />{/if}
      {#if state.deletion.pending}<p role="status">Deleting file…</p>{/if}
      {#if state.deletion.message}<p role="alert">{state.deletion.message}</p>{/if}
      {#if state.deletion.needsReload}<Button variant="secondary" onclick={state.deletion.reconcile}>{state.deletion.mutationSucceeded ? 'Reload parent folder' : 'Reload file'}</Button>{/if}
      {#if state.deletion.signInRequired}<Button variant="secondary" onclick={signIn}>Sign in</Button>{/if}
      <section class="metadata" aria-label="Metadata">
        <h2>Metadata</h2>
        <dl>
        <dt>Type</dt><dd>File</dd>
        <dt>Content type</dt><dd>{typeof state.node.metadata.content_type === 'string' ? state.node.metadata.content_type : 'Not specified'}</dd>
        <dt>Updated</dt><dd><time datetime={state.node.updated_at}>{updatedAt(state.node.updated_at)}</time></dd>
        {#each Object.entries(state.node.metadata.attributes) as [name, value] (name)}
          {#if name !== 'description'}<dt>{name}</dt><dd>{value}</dd>{/if}
        {/each}
        </dl>
      </section>
    </section>
  {/if}
{/if}

{#if state.sharing.dialog.open}<NodeSharingDialog state={state.sharing.dialog} {signIn} />{/if}
<p role="status" aria-atomic="true">{state.sharing.dialog.status}</p>
  {/snippet}
</FilesContainer>

<style>
  .file-drag-image { position: fixed; top: 0; left: 0; width: 1px; height: 1px; pointer-events: none; }
  .file-drag-preview { position: fixed; top: 0; left: 0; transform: translate(var(--preview-x), var(--preview-y)); z-index: 40; display: flex; align-items: center; gap: 0.75rem; box-sizing: border-box; width: min(18rem, calc(100vw - 1rem)); padding: 0.75rem; border: 1px solid var(--admin-accent); border-radius: var(--admin-radius); background: var(--admin-panel); color: var(--admin-accent); box-shadow: var(--admin-shadow); pointer-events: none; }
  .file-drag-label { min-width: 0; display: grid; gap: 0.2rem; }
  .file-drag-label span { color: var(--admin-muted); font-size: 0.75rem; }
  .file-drag-label strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--admin-ink); font-size: 0.9rem; font-weight: 500; }
  .page-file-drop { position: fixed; inset: 0; z-index: 1000; display: grid; place-items: center; padding: 1rem; background: rgb(30 35 33 / 65%); pointer-events: none; }
  .drop-prompt { box-sizing: border-box; width: min(100%, 32rem); padding: 2.5rem 1.5rem; border: 2px dashed var(--admin-accent); border-radius: var(--admin-radius); background: var(--admin-panel); text-align: center; color: var(--admin-ink); overflow-wrap: anywhere; }
  .drop-prompt svg { color: var(--admin-accent); }
  .drop-prompt p { line-height: 1.5; }
  .upload-status:empty, .drag-status:empty { margin: 0; }
  .drag-status:not(:empty) { position: fixed; bottom: 1rem; left: 50%; transform: translateX(-50%); z-index: 30; max-width: calc(100vw - 3rem); box-sizing: border-box; margin: 0; padding: 0.75rem 1rem; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-panel); color: var(--admin-ink); box-shadow: var(--admin-shadow); pointer-events: none; }
  .upload-status:not(:empty) { color: var(--admin-ink); }
  .availability-error { font-size: 0.9rem; }
  .node-identity { min-width: 0; }
  .node-identity h1 { margin-bottom: 0.35rem; }
  h1 { min-width: 0; overflow-wrap: anywhere; }
  a { color: var(--admin-accent); overflow-wrap: anywhere; }
  :focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
  .items { overflow-x: auto; --node-actions-trigger-size: 1.75rem; }
  table { width: 100%; min-width: 36rem; table-layout: fixed; border-collapse: collapse; text-align: left; font-size: 0.9rem; }
  .type-column { width: 6rem; }
  .updated-column { width: 12rem; }
  .actions-column { width: 5rem; }
  th, td { padding: 0.2rem 0.6rem; }
  th { padding-block: 0.5rem; border-bottom: 1px solid var(--admin-border); color: var(--admin-muted); font-weight: 500; }
  .item-row { position: relative; }
  .item-row:nth-child(even) { background: var(--admin-soft); }
  .item-row:hover, .item-row:focus-within { background: var(--admin-accent-soft); }
  .item-row.home-row { background: var(--admin-accent-soft); box-shadow: inset 3px 0 var(--admin-accent); }
  .home-row .item-name { font-weight: 600; }
  .item-row.drag-source { opacity: 0.6; }
  .item-row.drop-target { background: var(--admin-accent-soft); box-shadow: inset 0 0 0 2px var(--admin-accent); }
  .item-row[draggable='true'] .item-name { cursor: grab; }
  .item-row[draggable='true'] .item-name::after { cursor: grab; }
  .row-actions { text-align: right; white-space: nowrap; }
  .row-actions > :global(button) { position: relative; z-index: 1; }
  .item-name-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .items time { white-space: nowrap; }
  .row-name { display: flex; align-items: center; gap: 0.6rem; }
  .item-name { min-width: 0; display: flex; align-items: center; gap: 0.6rem; }
  .item-name::after { content: ''; position: absolute; inset: 0; cursor: pointer; }
  svg { flex-shrink: 0; }
  p, dt { color: var(--admin-muted); }
  [role='alert'] { color: var(--admin-danger); }
  .drop-prompt h2 { font-size: 1.15rem; overflow-wrap: anywhere; }
  dl { display: grid; grid-template-columns: minmax(6rem, 9rem) minmax(0, 1fr); gap: 0.75rem 1rem; margin: 1rem 0 0; font-size: 0.9rem; }
  dd { margin: 0; overflow-wrap: anywhere; }
  .metadata { border-top: 1px solid var(--admin-border); padding-top: 1rem; }
  .metadata h2 { margin: 0; font-size: 1rem; }
  @media (pointer: coarse) {
    .items { --node-actions-trigger-size: 2.75rem; }
  }
  @media (max-width: 480px) {
    dl { grid-template-columns: minmax(0, 1fr); gap: 0.35rem; }
    dd + dt { margin-top: 0.65rem; }
  }
  .visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
</style>
