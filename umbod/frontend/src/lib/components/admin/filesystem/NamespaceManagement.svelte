<script lang="ts">
  import AdminSaveAction from '../shared/AdminSaveAction.svelte';
  import Button from '../shared/Button.svelte';
  import DelayedSpinner from '../shared/DelayedSpinner.svelte';
  import LoadingButton from '../shared/LoadingButton.svelte';
  import ModalShell from '../../shared/ModalShell.svelte';
  import SegmentedRadio from '../../shared/SegmentedRadio.svelte';
  import NamespaceFormModal from './NamespaceFormModal.svelte';
  import type { NamespaceManagementState } from './namespace-management-state.svelte';

  let { state }: { state: NamespaceManagementState } = $props();
  const id = $props.id();
</script>

<section class="namespaces" aria-labelledby={id + '-title'}>
  <h3 id={id + '-title'}>Shared namespaces</h3>
  <DelayedSpinner active={state.busy && !state.editorOpen && !state.confirmingDelete} label="Updating namespaces" />
  {#if (state.error || state.needsReload) && !state.editorOpen}
    <div class="load-error">
      {#if state.error}<p role="alert">{state.error}</p>{/if}
      <Button variant="secondary" disabled={!state.canOpenEditor} onclick={state.requestReload}>Reload namespaces</Button>
    </div>
  {/if}
  {#if state.selectedGroupId === null}<p class="empty">Select a group to assign access.</p>{/if}
  <ul aria-label="Shared namespaces" aria-busy={state.busy}>
    {#each state.namespaces as namespace (namespace.id)}
      <li>
        <div class="namespace-identity">
          <span class="namespace-name">{namespace.name}</span>
          {#if namespace.description}<p class="namespace-description">{namespace.description}</p>{/if}
        </div>
        <div class="namespace-actions">
          {#if state.selectedGroupId !== null}
            <SegmentedRadio size="compact" label="Access" accessibleName={'Access to ' + namespace.name} options={state.accessOptions} value={state.access(namespace.id)} disabled={!state.canAssignAccess} onchange={(access) => state.stageAccess(namespace.id, access)} />
          {/if}
          <div class="metadata-actions">
            <Button class="namespace-edit" variant="secondary" size="compact" iconOnly aria-label={'Edit ' + namespace.name} title={'Edit ' + namespace.name} disabled={!state.canOpenEditor} onclick={() => state.beginEdit(namespace.id)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="m15 4 5 5M4 20l5-1L21 7a2.1 2.1 0 0 0-5-5L4 14zM4 20h16" /></svg>
            </Button>
            <Button variant="danger" size="compact" aria-label={'Delete namespace: ' + namespace.name} disabled={!state.canDelete} onclick={() => state.beginDelete(namespace.id)}>Delete namespace</Button>
          </div>
        </div>
      </li>
    {:else}
      {#if !state.busy && !state.error && !state.needsReload}<li class="empty">No shared namespaces</li>{/if}
    {/each}
  </ul>
  {#if state.reloadConfirmation}
    <div class="reload-warning" role="alert">
      <p>You have unsaved permission changes. Discard them or cancel before reloading namespaces.</p>
      <Button variant="danger" onclick={() => state.resolveReload('discard')}>Discard changes</Button>
      <Button variant="secondary" onclick={() => state.resolveReload('cancel')}>Cancel</Button>
    </div>
  {/if}
  {#if state.permissionError}<p role="alert">{state.permissionError}</p>{/if}
  <form class="permission-save" onsubmit={(event) => { event.preventDefault(); void state.savePermissions(); }}>
    <AdminSaveAction label="Save permissions" loadingLabel="Saving permissions..." loading={state.savingPermissions} disabled={!state.canSavePermissions} message={state.permissionFeedback.message} tone={state.permissionFeedback.tone} icon={state.permissionFeedback.icon} />
  </form>
</section>

{#if state.editorOpen}<NamespaceFormModal {state} />{/if}
{#if state.confirmingDelete}
  <ModalShell title="Delete namespace?" titleId={id + '-delete-title'} descriptionId={id + '-delete-description'} close={state.cancelDelete} closeDisabled={state.busy} role="alertdialog">
    <p class="delete-description" id={id + '-delete-description'}>Delete <strong>{state.deleteName}</strong>? Only empty namespaces can be deleted.</p>
    <div class="delete-actions">
      <Button variant="secondary" data-dialog-cancel disabled={state.busy} onclick={state.cancelDelete}>Cancel</Button>
      <LoadingButton variant="danger" label="Delete namespace" loadingLabel="Deleting namespace" loading={state.busy} onclick={state.confirmDelete} />
    </div>
  </ModalShell>
{/if}

<style>
  .permission-save { display: flex; justify-content: flex-end; }
  .reload-warning { background: var(--admin-warning-bg); border: 1px solid var(--admin-warning-border); border-radius: var(--admin-radius); color: var(--admin-warning-text); padding: 1rem; }
  .namespaces { display: grid; gap: 1rem; }
  h3 { font-size: 0.9375rem; margin: 0; }
  ul { list-style: none; margin: 0; padding: 0; }
  li { align-items: center; border-top: 1px solid var(--admin-border); display: flex; flex-wrap: wrap; gap: 1rem; justify-content: space-between; padding: 1rem 0; }
  .namespace-identity { flex: 1; min-width: 0; }
  .namespace-description { color: var(--admin-muted); font-size: 0.875rem; margin: 0.35rem 0 0; overflow-wrap: anywhere; white-space: pre-wrap; }
  .namespace-name { font-size: 0.9375rem; font-weight: 600; min-width: 0; overflow-wrap: anywhere; }
  .namespace-actions { align-items: flex-end; display: flex; gap: 0.75rem; min-width: 0; }
  .metadata-actions, .delete-actions { display: flex; flex-wrap: wrap; gap: 0.75rem; justify-content: flex-end; }
  .metadata-actions :global(.namespace-edit) { height: 2.25rem; width: 2.25rem; }
  .delete-description { overflow-wrap: anywhere; }
  @media (max-width: 680px) {
    li { display: grid; grid-template-columns: minmax(0, 1fr) auto; }
    .namespace-actions { display: contents; }
    .namespace-actions :global(fieldset) { grid-column: 1 / -1; grid-row: 2; }
    .metadata-actions { align-self: center; grid-column: 2; grid-row: 1; }
  }
  .empty { color: var(--admin-muted); font-size: 0.875rem; margin: 0; }
  [role='alert'] { color: var(--admin-danger-text); }
  svg { display: block; height: 1.125rem; width: 1.125rem; }
</style>
