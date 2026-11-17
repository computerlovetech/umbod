<script lang="ts">
  import Button from '#lib/components/admin/shared/Button.svelte';
  import DelayedLoadingOverlay from '#lib/components/admin/shared/DelayedLoadingOverlay.svelte';
  import { filesHref, type FilesState } from '#lib/files/state/files-state.svelte.js';
  import type { NewFolderState } from '#lib/files/state/new-folder-state.svelte.js';
  import type { UploadState } from '#lib/files/state/upload-state.svelte.js';
  import { FileDropState } from '#lib/files/state/file-drop-state.svelte.js';
  import PermissionBadge from './PermissionBadge.svelte';
  import NodeActions from './NodeActions.svelte';
  import NodeSharingDialog from './NodeSharingDialog.svelte';
  import FilesNavigation from './FilesNavigation.svelte';
  import FileUploadForm from './FileUploadForm.svelte';
  import PageContainer from '#lib/components/shared/workspace/PageContainer.svelte';
  import AdminSplitWorkspace from '#lib/components/admin/shared/AdminSplitWorkspace.svelte';
  import FilesLocations from './FilesLocations.svelte';
  import FileTypeIcon from './FileTypeIcon.svelte';
  import { fileTypeIcon } from './file-type-icons';
  import NewFolderForm from './NewFolderForm.svelte';
  import FilePreview from './preview/FilePreview.svelte';

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
    return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'UTC' }).format(new Date(timestamp)) + ' UTC';
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

<PageContainer>
  {#snippet identity()}
    <div class="node-identity">
      <h1 id="files-heading" class="admin-title" tabindex="-1" {@attach state.rowDeletion.attachFocus}>Files</h1>
      <div class="location-navigation">
        {#if state.node}
          <FilesNavigation state={state.navigation} {signIn} />
        {/if}
      </div>
    </div>
  {/snippet}
  {#snippet actions()}
    <div class="location-actions" role="group" aria-label="Location actions">
    {#if state.node?.kind === 'directory'}
      {#if state.uploadAvailability === 'allowed'}
        <Button variant="quiet" iconOnly id="upload-file-button" aria-label="Upload file" title="Upload file" onclick={upload.show} disabled={!upload.available || upload.open}>
          <svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5" /></svg>
        </Button>
      {/if}
      {#if state.createDirectoryAllowed}
        <Button variant="quiet" iconOnly id="new-folder-button" aria-label="New folder" title="New folder" onclick={folder.show} disabled={state.phase !== 'ready' || folder.open}>
          <svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7V4h6l2 3h10v13H3V7Zm9 4v6m-3-3h6" /></svg>
        </Button>
      {/if}
    {/if}
    {#if state.node}<NodeActions disabled={state.phase !== 'ready'} contextKey={state.navigationVersion} update={state.update} description={state.description} name={state.locationName} displayName={state.atPersonalRoot ? state.locationName : undefined} node={state.node} sharing={state.atNamespaceRoot ? undefined : state.sharing} deletion={state.node.kind === 'file' ? state.deletion : undefined} mutationsAllowed={!state.atPersonalRoot} {signIn} />{/if}
    </div>
  {/snippet}
  {#snippet children()}
<AdminSplitWorkspace ariaLabel="Files workspace" sidebarLabel="Locations" sidebarHeading="Locations" detailLabel="Files content" --split-workspace-detail-padding="0">
  {#snippet sidebar()}
    <FilesLocations {state} {signIn} />
  {/snippet}
  {#snippet detail()}
    {#if state.contentLoading}<p class="visually-hidden" role="status">{state.phase === 'loading' ? 'Loading files…' : 'Loading preview…'}</p>{/if}
    <div class="files-view">
    <DelayedLoadingOverlay active={state.contentLoading} label={state.phase === 'loading' ? 'Loading files…' : 'Loading preview…'}>
    <div aria-busy={state.contentLoading} inert={state.contentLoading}>
<p class="upload-status" role="status" aria-atomic="true">{upload.pending ? 'Uploading file…' : upload.status}</p>

{#if state.mutationNotice}<p role="status">{state.mutationNotice}</p>{/if}
<p class="drag-status" role="status" aria-atomic="true">{state.dragMove.status}</p>
{#if state.dragMove.error}<p role="alert">{state.dragMove.error}</p>{/if}
{#if state.dragMove.needsReload}<Button variant="secondary" onclick={state.dragMove.reload} disabled={state.dragMove.pending}>Reload folder</Button>{/if}

{#if state.phase !== 'ready' && state.phase !== 'loading'}
  <p role="alert">{state.phase === 'denied' ? "You don't have access to this location." : state.phase === 'sign-in' ? 'Sign in to view files.' : state.phase === 'missing' ? 'This location is unavailable.' : "Couldn't load files."}</p>
  {#if state.phase === 'sign-in'}
    <Button variant="secondary" onclick={signIn}>Sign in</Button>
  {:else}
    <Button variant="secondary" onclick={folder.reload}>Retry</Button>
  {/if}
{/if}
{#if state.node}
  {#if state.node.kind === 'directory'}
    <div class="directory-tools">
    {#if !upload.available && upload.error}<p role="alert">{upload.error}</p>{/if}
    {#if state.uploadAvailability === 'sign-in'}
      <p class="availability-error">Sign in to check upload availability. <Button variant="quiet" size="compact" onclick={signIn}>Sign in</Button></p>
    {/if}
    {#if upload.open && upload.available}<FileUploadForm state={upload} destination={state.locationName} {signIn} />{/if}
    {#if folder.open}<NewFolderForm state={folder} />{/if}
    </div>
    {#if state.children.length === 0}
      <p class="empty-folder" role="status">This folder is empty.</p>
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
                <td><time datetime={item.updated_at} title={item.updated_at}>{updatedAt(item.updated_at)}</time></td>
                <td class="row-actions">
                  {#if editing}<NodeActions disabled={state.phase !== 'ready'} contextKey={state.navigationVersion} update={editing.update} description={editing.description} name={presentation.name} displayName={presentation.isHome ? presentation.name : undefined} node={item} sharing={state.sharing} {deletion} onconfirm={() => { void state.rowDeletion.confirm(item.id); }} {signIn} />{/if}
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
      {#if state.deletion.pending}<p role="status">Deleting file…</p>{/if}
      {#if state.deletion.message}<p role="alert">{state.deletion.message}</p>{/if}
      {#if state.deletion.needsReload}<Button variant="secondary" onclick={state.deletion.reconcile}>{state.deletion.mutationSucceeded ? 'Reload parent folder' : 'Reload file'}</Button>{/if}
      {#if state.deletion.signInRequired}<Button variant="secondary" onclick={signIn}>Sign in</Button>{/if}
      {#if !state.contentLoading}
      <div class="file-preview-surface">
        <section class="metadata" aria-label="Metadata">
          <dl class="metadata-grid">
            <div><dt>Name</dt><dd class="metadata-filename" title={state.node.name}><span class="metadata-icon" aria-hidden="true"><FileTypeIcon kind="file" name={state.node.name} contentType={state.node.metadata.content_type} size={16} /></span><span class="metadata-filename-label">{state.node.name}</span></dd></div>
            <div><dt title="Content type">Type</dt><dd title={typeof state.node.metadata.content_type === 'string' ? state.node.metadata.content_type : undefined}><span class="metadata-type-label">{fileTypeIcon('file', state.node.name, state.node.metadata.content_type).label}</span></dd></div>
            <div><dt>Updated</dt><dd class="metadata-updated"><time datetime={state.node.updated_at} title={state.node.updated_at}>{updatedAt(state.node.updated_at)}</time></dd></div>
          </dl>
          <dl class="metadata-attributes">
            {#each Object.entries(state.node.metadata.attributes) as [name, value] (name)}
              {#if name !== 'description'}<div><dt>{name}</dt><dd>{value}</dd></div>{/if}
            {/each}
          </dl>
        </section>
        {#if state.preview}
          <div class="preview-document"><FilePreview state={state.preview} {signIn} /></div>
        {/if}
      </div>
      {/if}
    </section>
  {/if}
{/if}

{#if state.sharing.dialog.open}<NodeSharingDialog state={state.sharing.dialog} {signIn} />{/if}
<p role="status" aria-atomic="true">{state.sharing.dialog.status}</p>
    </div>
    </DelayedLoadingOverlay>
    </div>
  {/snippet}
</AdminSplitWorkspace>
  {/snippet}
</PageContainer>

<style>
  .location-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: inherit; width: calc(76px + 2.75rem + 1.2rem); min-height: 2.75rem; }
  .files-view { --files-type-width: 10rem; --files-updated-width: 12rem; --files-actions-width: 5rem; --files-cell-padding: 1rem; display: grid; grid-template-columns: minmax(0, 1fr); min-width: 0; height: 100%; }
  .location-navigation { flex: 1; min-width: 0; }
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
  .directory-tools:has(> *) { padding: 1rem; }
  .empty-folder { margin: 0; padding: 1rem; }
  .node-identity { display: flex; align-items: center; gap: 1.5rem; min-width: 0; min-height: 2.75rem; }
  .node-identity h1 { flex-shrink: 0; }
  h1 { min-width: 0; overflow-wrap: anywhere; }
  a { color: var(--admin-accent); overflow-wrap: anywhere; }
  :focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
  .items { overflow-x: auto; --node-actions-trigger-size: 1.75rem; }
  table { width: 100%; min-width: 36rem; table-layout: fixed; border-collapse: separate; border-spacing: 0; text-align: left; font-size: 0.9rem; line-height: 1.4; }
  .type-column { width: var(--files-type-width); }
  .updated-column { width: var(--files-updated-width); }
  .actions-column { width: var(--files-actions-width); }
  th, td { padding: 0.2rem var(--files-cell-padding); }
  th, .metadata-grid dt { margin: 0; padding: 0.5rem var(--files-cell-padding); border-bottom: 1px solid var(--admin-border); color: var(--admin-muted); font-size: 0.9rem; font-weight: 500; line-height: 1.4; }
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
  p { color: var(--admin-muted); }
  [role='alert'] { color: var(--admin-danger); }
  .drop-prompt h2 { font-size: 1.15rem; overflow-wrap: anywhere; }
  .file-preview-surface { min-width: 0; background: var(--admin-panel); }
  .metadata { min-width: 0; container-type: inline-size; }
  .metadata-grid { display: grid; grid-template-columns: minmax(0, 1fr) var(--files-type-width) calc(var(--files-updated-width) + var(--files-actions-width)); margin: 0; }
  .metadata-grid > div { min-width: 0; }
  .metadata-attributes dt { color: var(--admin-muted); font-size: 0.65rem; line-height: 1.4; margin-bottom: 0.3rem; }
  .metadata dd { margin: 0; color: var(--admin-ink); font-size: 0.75rem; line-height: 1.5; }
  .metadata-grid dd { padding: 0.4rem var(--files-cell-padding); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.9rem; line-height: 1.4; }
  .metadata-filename { display: flex; align-items: center; gap: 0.5rem; font-weight: 500; }
  .metadata-icon { display: flex; flex-shrink: 0; color: var(--admin-muted); }
  .metadata-filename-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
  .metadata-type-label, .metadata-updated time { color: var(--admin-muted); font-size: 0.8125rem; }
  .metadata time { font-variant-numeric: tabular-nums; }
  .metadata-attributes { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 10rem), 1fr)); gap: 0.75rem 1rem; margin: 0; padding: 0.5rem var(--files-cell-padding) 0.85rem; }
  .metadata-attributes:empty { display: none; }
  .metadata-attributes dd { overflow-wrap: anywhere; }
  .preview-document { min-width: 0; min-height: 16rem; padding: 1.5rem; border-top: 1px solid var(--admin-border); }
  @media (pointer: coarse) {
    .items { --node-actions-trigger-size: 2.75rem; }
  }
  @container (max-width: 640px) {
    .metadata-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .metadata-grid > div:first-child { grid-column: 1 / -1; }
    .metadata-grid dd { white-space: normal; overflow-wrap: anywhere; }
  }
  @media (max-width: 480px) {
    .preview-document { padding: 1rem; }
  }
  .visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
</style>
