<script lang="ts">
  import Button from '../shared/Button.svelte';
  import AdminRecordList from '../shared/AdminRecordList.svelte';
  import DelayedSpinner from '../shared/DelayedSpinner.svelte';
  import LoadingButton from '../shared/LoadingButton.svelte';
  import ModalShell from '../../shared/ModalShell.svelte';
  import NamespaceFormModal from './NamespaceFormModal.svelte';
  import type { NamespaceManagementState } from './namespace-management-state.svelte';

  let { state }: { state: NamespaceManagementState } = $props();
  const id = $props.id();
</script>

<section class="namespaces" aria-label="Namespace management" aria-busy={state.busy}>
  <DelayedSpinner active={state.busy && !state.editorOpen && !state.confirmingDelete} label="Updating namespaces" />
  {#if (state.error || state.needsReload) && !state.editorOpen}
    <div class="load-error">
      {#if state.error}<p role="alert">{state.error}</p>{/if}
      <Button variant="secondary" disabled={!state.canOpenEditor} onclick={state.requestReload}>Reload namespaces</Button>
    </div>
  {/if}
  {#if state.namespaces.length || (state.inventoryLoaded && !state.busy && !state.needsReload)}
    <AdminRecordList items={state.namespaces} keyOf={(namespace) => namespace.id} label="Shared namespaces" recordHeading="Namespace" detailHeading="Groups with access" emptyMessage="No shared namespaces">
      {#snippet identity(namespace)}
        <div class="namespace-identity">
          <span class="namespace-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M3 6a2 2 0 0 1 2-2h4l3 3h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" /></svg></span>
          <div>
            <h2>{namespace.name}</h2>
            {#if namespace.description}<p class="namespace-description">{namespace.description}</p>{/if}
          </div>
        </div>
      {/snippet}
      {#snippet detail(namespace)}
        <span class="group-count">{namespace.groups.length} {namespace.groups.length === 1 ? 'group' : 'groups'}</span>
      {/snippet}
      {#snippet actions(namespace)}
        <Button variant="secondary" iconOnly aria-label={'Edit ' + namespace.name} title={'Edit ' + namespace.name} disabled={!state.canOpenEditor} onclick={() => state.beginEdit(namespace.id)}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="m15 4 5 5M4 20l5-1L21 7a2.1 2.1 0 0 0-5-5L4 14zM4 20h16" /></svg>
        </Button>
        <Button variant="danger" iconOnly aria-label={'Delete namespace: ' + namespace.name} title={'Delete namespace: ' + namespace.name} disabled={!state.canDelete} onclick={() => state.beginDelete(namespace.id)}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M3 6h18M9 6V4h6v2M5 6l1 14h12l1-14M10 10v6M14 10v6" /></svg>
        </Button>
      {/snippet}
    </AdminRecordList>
  {/if}
  <a class="permissions-link" href="/admin/group-permissions/filesystem">Manage group access</a>
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
  .namespaces { display: grid; gap: 1rem; }
  .namespace-identity { align-items: center; display: flex; gap: .75rem; min-width: 0; }
  .namespace-icon { background: var(--admin-soft); border-radius: var(--admin-radius); color: var(--admin-muted); display: grid; flex: none; height: 2.25rem; place-items: center; width: 2.25rem; }
  h2 { font-size: .9375rem; margin: 0; overflow-wrap: anywhere; }
  .namespace-description { color: var(--admin-muted); font-size: .875rem; margin: .2rem 0 0; overflow-wrap: anywhere; white-space: pre-wrap; }
  .group-count { background: var(--admin-soft); border-radius: 999px; color: var(--admin-muted); display: inline-block; font-size: .8125rem; padding: .2rem .6rem; }
  .permissions-link { color: var(--admin-muted); font-size: .875rem; justify-self: start; }
  .delete-actions { display: flex; flex-wrap: wrap; gap: .75rem; justify-content: flex-end; }
  .delete-description { overflow-wrap: anywhere; }
  [role='alert'] { color: var(--admin-danger-text); }
  svg { display: block; height: 1.125rem; width: 1.125rem; }
</style>
