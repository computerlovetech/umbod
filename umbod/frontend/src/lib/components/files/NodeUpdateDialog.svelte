<script lang="ts">
  import Button from '$lib/components/admin/shared/Button.svelte';
  import ModalShell from '$lib/components/shared/ModalShell.svelte';
  import LoadingButton from '$lib/components/admin/shared/LoadingButton.svelte';
  import type { NodeUpdateState } from '$lib/files/state/node-update-state.svelte';
  import type { DestinationFolder } from '$lib/files/state/move-destination-state.svelte';
  import { FolderPickerFocusState } from './folder-picker-focus-state.svelte';

  let { state }: { state: NodeUpdateState } = $props();

  const disclosureFocus = new FolderPickerFocusState();
</script>

{#snippet folders(items: readonly DestinationFolder[])}
  {#each items as folder (folder.id)}
    <li>
      <div class={['folder-row', { selected: folder.selected }]} role="group" aria-label={folder.name}>
        <div class="disclosure">
          {#if folder.expandable || disclosureFocus.isFocused(folder.id)}
            <button type="button" class="expand-button" aria-label={folder.expandable ? `${folder.expanded ? 'Collapse' : 'Expand'} ${folder.name}` : `No subfolders in ${folder.name}`} aria-expanded={folder.expandable ? folder.expanded : undefined} aria-disabled={!folder.expandable} disabled={state.pending || state.needsReload} onfocus={() => disclosureFocus.focus(folder.id)} onblur={() => disclosureFocus.blur(folder.id)} onclick={() => { if (folder.expandable) void state.destinations.toggle(folder.id); }}>
              <svg class={['chevron', { expanded: folder.expanded }]} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="m9 6 6 6-6 6" /></svg>
            </button>
          {/if}
        </div>
        <button class="folder-button" type="button" aria-label={`Select ${folder.name}`} aria-pressed={folder.selected} disabled={!folder.selectable || state.pending || state.needsReload} onclick={() => { void state.destinations.select(folder.id); }}>
          <svg class="folder-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M3 7V5a1 1 0 0 1 1-1h5l2 3h9a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7Z" /></svg>
          <span class="folder-name">{folder.name}</span>
          {#if folder.current}
            <span class="badge">Current</span>
          {:else if !folder.selectable}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" role="img" aria-label="Read only"><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>
          {/if}
          {#if folder.selected}
            <svg class="check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m5 12 4 4L19 6" /></svg>
          {/if}
        </button>
      </div>
      {#if folder.expanded}
        {#if folder.phase === 'loading'}
          <p class="branch-message" role="status">Loading folders…</p>
        {:else if folder.phase === 'error'}
          <div class="branch-message">
            <span role="alert">Could not load folders.</span>
            <Button variant="quiet" type="button" disabled={state.pending || state.needsReload} onclick={() => { void state.destinations.retryBranch(folder.id); }} aria-label={`Retry ${folder.name}`}>Retry</Button>
          </div>
        {/if}
        {#if folder.children.length > 0}
          <ul class="children" aria-label={`Folders in ${folder.name}`}>{@render folders(folder.children)}</ul>
        {/if}
      {/if}
    </li>
  {/each}
{/snippet}

<ModalShell title={state.title} titleId="node-update-title" close={state.cancel} closeDisabled={state.pending} initialFocus={state.moving ? '[data-dialog-cancel]' : '#node-rename'} --modal-padding="0" --modal-header-padding="1.25rem 1.5rem 1rem">
  <form aria-label={state.moving ? 'Move item' : 'Rename item'} onsubmit={(event) => { event.preventDefault(); void state.submit(); }}>
    <div class="dialog-body">
      {#if state.moving}
        <div class="folder-picker" role="region" aria-label="Destination folders" aria-busy={state.destinations.loading}>
          <ul aria-label="Choose destination">{@render folders(state.destinations.folders)}</ul>
          {#if state.destinations.loading && state.destinations.folders.length === 0}<p class="branch-message" role="status">Loading folders…</p>{/if}
        </div>
        {#if state.destinations.canRetry}<Button variant="secondary" type="button" onclick={state.destinations.retry} disabled={state.pending}>Retry folders</Button>{/if}
      {:else}
        <label for="node-rename">Name</label>
        <input id="node-rename" value={state.draft} oninput={(event) => state.changeName(event.currentTarget.value)} disabled={state.pending || state.needsReload} required />
      {/if}
      {#if state.error}<p role="alert">{state.error}</p>{/if}
      {#if state.needsReload}<Button variant="secondary" type="button" onclick={state.reload} disabled={state.pending}>Reload item</Button>{/if}
    </div>
    <footer class="actions">
      <Button variant="secondary" type="button" data-dialog-cancel onclick={state.cancel} disabled={state.pending}>Cancel</Button>
      <LoadingButton class="destination-confirm" type="submit" loading={state.pending || state.destinations.selecting} disabled={!state.canSubmit} label={state.submitLabel} loadingLabel={state.pending ? 'Saving…' : 'Checking…'} />
    </footer>
  </form>
</ModalShell>

<style>
  p { margin: 0; overflow-wrap: anywhere; }
  form { display: flex; flex: 1; flex-direction: column; min-height: 0; text-align: start; white-space: normal; font-size: 0.9rem; line-height: 1.5; }
  .dialog-body { display: flex; flex-direction: column; gap: 0.75rem; min-height: 0; overflow: auto; padding: 0.25rem 1.5rem 1.25rem; }
  label { display: block; font-weight: 500; }
  input { box-sizing: border-box; min-width: 0; width: 100%; padding: 0.6rem; background: var(--admin-panel); color: var(--admin-ink); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); font: inherit; }
  .actions { display: flex; flex-wrap: wrap; flex-shrink: 0; justify-content: flex-end; gap: 0.65rem; padding: 1rem 1.5rem; border-top: 1px solid var(--admin-border); }
  .actions :global(.destination-confirm) { max-width: 100%; min-width: 0; white-space: normal; overflow-wrap: anywhere; }
  .folder-picker { max-height: min(45dvh, 24rem); overflow: auto; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: 0.35rem; }
  ul { list-style: none; padding: 0; margin: 0; }
  .children { margin-inline-start: 1.25rem; padding-inline-start: 0.35rem; border-inline-start: 1px solid var(--admin-border); }
  .folder-row { display: flex; align-items: stretch; border: 1px solid transparent; border-radius: var(--admin-radius); }
  .folder-row:hover { background: var(--admin-canvas); }
  .folder-row.selected { background: color-mix(in srgb, var(--admin-accent) 10%, var(--admin-panel)); border-color: var(--admin-accent); }
  .disclosure { display: flex; align-items: center; flex: 0 0 2rem; }
  .expand-button, .folder-button { display: flex; align-items: center; background: transparent; color: var(--admin-ink); border: 0; border-radius: var(--admin-radius); font: inherit; cursor: pointer; text-align: start; }
  .expand-button { justify-content: center; width: 2rem; min-height: 2.75rem; padding: 0; }
  .expand-button:hover:not(:disabled) { background: color-mix(in srgb, var(--admin-ink) 8%, transparent); }
  .folder-button { gap: 0.65rem; flex: 1; min-width: 0; min-height: 2.75rem; padding: 0.5rem 0.65rem 0.5rem 0.15rem; }
  .folder-button:disabled { cursor: default; color: var(--admin-muted); }
  .expand-button:disabled, .expand-button[aria-disabled='true'] { cursor: default; opacity: 0.6; }
  .folder-name { flex: 1; min-width: 0; overflow-wrap: anywhere; }
  .badge { flex-shrink: 0; padding: 0.1rem 0.4rem; background: var(--admin-canvas); border: 1px solid var(--admin-border); border-radius: 999px; color: var(--admin-muted); font-size: 0.7rem; }
  svg { width: 1.15rem; height: 1.15rem; flex-shrink: 0; }
  .folder-icon { color: var(--admin-accent); }
  .chevron { color: var(--admin-muted); }
  .chevron.expanded { transform: rotate(90deg); }
  .check { color: var(--admin-accent); }
  .branch-message { display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0.75rem 0.5rem 2.25rem; color: var(--admin-muted); }
  [role='alert'] { color: var(--admin-danger); }
  :focus-visible { outline: 2px solid var(--admin-accent); outline-offset: -2px; }
  @media (max-width: 480px) {
    .dialog-body, .actions { padding-inline: 1rem; }
    .children { margin-inline-start: 0.65rem; }
    input { font-size: 1rem; }
  }
</style>
