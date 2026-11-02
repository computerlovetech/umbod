<script lang="ts">
  import { nativeDialog } from '$lib/components/shared/dialogs/native-dialog';
  import LoadingButton from '$lib/components/admin/shared/LoadingButton.svelte';
  import type { NodeUpdateState } from '$lib/files/state/node-update-state.svelte';

  let { state }: { state: NodeUpdateState } = $props();
</script>

<dialog aria-labelledby="node-update-title" {@attach nativeDialog(state.cancel, () => !state.pending, state.moving ? '[data-dialog-cancel]' : '#node-rename')}>
  <h2 id="node-update-title">{state.moving ? 'Move item' : 'Rename item'}</h2>
  <form aria-label={state.moving ? 'Move item' : 'Rename item'} onsubmit={(event) => { event.preventDefault(); void state.submit(); }}>
    {#if state.moving}
      <nav aria-label="Destination path">
        {#each state.navigation.path?.items ?? [] as item (item.id)}
          <button type="button" onclick={() => { void state.browse(item.id); }} disabled={state.pending || state.loading}>{state.navigation.label(item)}</button>
        {/each}
      </nav>
      <p>Destination: {state.folder?.name || 'Files'}</p>
      <p>Open a folder to browse. Only writable destinations can be selected.</p>
      {#if state.loading}<p role="status">Loading folders…</p>{/if}
      <ul aria-label="Destination folders">
        {#each state.folders as folder (folder.id)}
          <li><button type="button" onclick={() => { void state.browse(folder.id); }} disabled={state.pending || state.loading}>Open {folder.name}</button></li>
        {/each}
      </ul>
      {#if state.folder}<button type="button" onclick={() => { void state.browse(state.folder!.id); }} disabled={state.pending || state.loading}>Retry folder</button>{/if}
      <label for="move-folder-id">Folder ID</label>
      <input id="move-folder-id" value={state.directFolderId} oninput={(event) => state.changeFolderId(event.currentTarget.value)} disabled={state.pending} />
      <button type="button" onclick={state.openDirectFolder} disabled={state.pending || state.loading}>Open folder ID</button>
    {:else}
      <label for="node-rename">Name</label>
      <input id="node-rename" value={state.draft} oninput={(event) => state.changeName(event.currentTarget.value)} disabled={state.pending || state.needsReload} required />
    {/if}
    {#if state.error}<p role="alert">{state.error}</p>{/if}
    {#if state.needsReload}<button type="button" onclick={state.reload} disabled={state.pending}>Reload item</button>{/if}
    <div class="actions">
      <button type="button" data-dialog-cancel onclick={state.cancel} disabled={state.pending}>Cancel</button>
      <LoadingButton type="submit" loading={state.pending} disabled={!state.canSubmit} label={state.moving ? 'Move here' : 'Rename'} loadingLabel="Saving…" />
    </div>
  </form>
</dialog>

<style>
  dialog { box-sizing: border-box; width: min(36rem, calc(100% - 2rem)); max-height: calc(100dvh - 2rem); overflow: auto; padding: 1.5rem; background: var(--admin-panel); color: var(--admin-ink); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); box-shadow: var(--admin-shadow-dialog); }
  dialog::backdrop { background: var(--admin-overlay); }
  h2, p { overflow-wrap: anywhere; }
  label { display: block; margin-block: 1rem 0.4rem; }
  input { box-sizing: border-box; width: 100%; padding: 0.6rem; background: var(--admin-panel); color: var(--admin-ink); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); font: inherit; }
  button { padding: 0.6rem 0.9rem; background: var(--admin-panel); color: var(--admin-ink); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); font: inherit; cursor: pointer; }
  button:disabled { opacity: 0.6; cursor: default; }
  .actions { display: flex; justify-content: flex-end; gap: 1rem; margin-top: 1.5rem; }
  nav { display: flex; flex-wrap: wrap; gap: 0.4rem; }
  ul { list-style: none; padding: 0; }
  li { margin-block: 0.4rem; }
  [role='alert'] { color: var(--admin-danger); }
  :focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
</style>
