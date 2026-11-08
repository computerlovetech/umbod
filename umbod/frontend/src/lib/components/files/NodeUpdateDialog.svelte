<script lang="ts">
  import Button from '$lib/components/admin/shared/Button.svelte';
  import ModalShell from '$lib/components/shared/ModalShell.svelte';
  import LoadingButton from '$lib/components/admin/shared/LoadingButton.svelte';
  import type { NodeUpdateState } from '$lib/files/state/node-update-state.svelte';

  let { state }: { state: NodeUpdateState } = $props();
</script>

<ModalShell title={state.moving ? 'Move item' : 'Rename item'} titleId="node-update-title" close={state.cancel} closeDisabled={state.pending} initialFocus={state.moving ? '[data-dialog-cancel]' : '#node-rename'} --modal-padding="0" --modal-header-padding="1.25rem 1.5rem 1rem">
  <form aria-label={state.moving ? 'Move item' : 'Rename item'} onsubmit={(event) => { event.preventDefault(); void state.submit(); }}>
    <div class="dialog-body">
      {#if state.moving}
        <p class="hint">Choose a destination folder, then select Move here.</p>
        <nav aria-label="Destination path">
          {#each state.navigation.displayItems as item (item.id)}
            <button class="path-button" type="button" onclick={() => { void state.browse(item.id); }} disabled={state.pending || state.loading}>{state.navigation.label(item)}</button>
          {/each}
        </nav>
        <p class="destination">Destination: <strong>{state.destinationName}</strong></p>
        <p class="hint" id="destination-hint">Open a folder to browse. Only writable destinations can be selected.</p>
        <div class="folder-browser" aria-busy={state.loading} aria-describedby="destination-hint" role="region" aria-label="Folder browser">
          {#if state.loading}<p class="browser-message" role="status">Loading folders…</p>{/if}
          <ul aria-label="Destination folders">
            {#each state.folders as folder (folder.id)}
              <li>
                <button class="folder-button" type="button" aria-label={`Open ${folder.name}`} onclick={() => { void state.browse(folder.id); }} disabled={state.pending || state.loading}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M3 7V5a1 1 0 0 1 1-1h5l2 3h9a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7Z" /></svg>
                  <span>{folder.name}</span>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m9 6 6 6-6 6" /></svg>
                </button>
              </li>
            {/each}
          </ul>
          {#if !state.loading && !state.error && state.folders.length === 0}<p class="browser-message">No subfolders in this folder.</p>{/if}
        </div>
        {#if state.error}<Button variant="secondary" type="button" onclick={state.retryBrowse} disabled={state.pending || state.loading}>Retry folder</Button>{/if}
      {:else}
        <label for="node-rename">Name</label>
        <input id="node-rename" value={state.draft} oninput={(event) => state.changeName(event.currentTarget.value)} disabled={state.pending || state.needsReload} required />
      {/if}
      {#if state.error}<p role="alert">{state.error}</p>{/if}
      {#if state.needsReload}<Button variant="secondary" type="button" onclick={state.reload} disabled={state.pending}>Reload item</Button>{/if}
    </div>
    <footer class="actions">
      <Button variant="secondary" type="button" data-dialog-cancel onclick={state.cancel} disabled={state.pending}>Cancel</Button>
      <LoadingButton type="submit" loading={state.pending} disabled={!state.canSubmit} label={state.moving ? 'Move here' : 'Rename'} loadingLabel="Saving…" />
    </footer>
  </form>
</ModalShell>

<style>
  p { overflow-wrap: anywhere; }
  p { margin: 0; }
  .hint { color: var(--admin-muted); font-size: 0.85rem; }
  form { display: flex; flex: 1; flex-direction: column; min-height: 0; text-align: start; white-space: normal; font-size: 0.9rem; line-height: 1.5; }
  .dialog-body { display: flex; flex-direction: column; gap: 0.75rem; min-height: 0; overflow: auto; padding: 0.25rem 1.5rem 1.25rem; }
  label { display: block; font-weight: 500; }
  input { box-sizing: border-box; min-width: 0; width: 100%; padding: 0.6rem; background: var(--admin-panel); color: var(--admin-ink); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); font: inherit; }
  .path-button, .folder-button { background: var(--admin-panel); color: var(--admin-ink); border: 0; font: inherit; cursor: pointer; text-align: start; overflow-wrap: anywhere; white-space: normal; }
  .path-button:disabled, .folder-button:disabled { opacity: 0.6; cursor: default; }
  .path-button:hover:not(:disabled), .folder-button:hover:not(:disabled) { background: var(--admin-canvas); }
  .actions { display: flex; flex-wrap: wrap; flex-shrink: 0; justify-content: flex-end; gap: 0.65rem; padding: 1rem 1.5rem; border-top: 1px solid var(--admin-border); }
  nav { display: flex; flex-wrap: wrap; align-items: center; gap: 0.25rem; }
  .path-button { max-width: 100%; min-height: 2.25rem; padding: 0.35rem 0.6rem; border-radius: var(--admin-radius); color: var(--admin-accent); }
  nav .path-button + .path-button::before { content: '/'; margin-inline-end: 0.6rem; color: var(--admin-muted); }
  .folder-browser { flex-shrink: 0; max-height: min(32dvh, 15rem); min-height: 6rem; overflow: auto; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); }
  ul { list-style: none; padding: 0; margin: 0; }
  li + li { border-top: 1px solid var(--admin-border); }
  .folder-button { display: flex; align-items: center; gap: 0.75rem; width: 100%; min-height: 2.75rem; padding: 0.65rem 0.75rem; }
  .folder-button span { flex: 1; min-width: 0; }
  svg { width: 1.15rem; height: 1.15rem; flex-shrink: 0; color: var(--admin-muted); }
  .browser-message { padding: 1rem; color: var(--admin-muted); }
  [role='alert'] { color: var(--admin-danger); }
  :focus-visible { outline: 2px solid var(--admin-accent); outline-offset: -2px; }
  @media (max-width: 480px) {
    .dialog-body, .actions { padding-inline: 1rem; }
    input { font-size: 1rem; }
  }
</style>
