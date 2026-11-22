<script lang="ts">
  import AdminPermissionRow from '../shared/AdminPermissionRow.svelte';
  import AdminSaveAction from '../shared/AdminSaveAction.svelte';
  import Button from '../shared/Button.svelte';
  import DelayedSpinner from '../shared/DelayedSpinner.svelte';
  import SegmentedRadio from '../../shared/SegmentedRadio.svelte';
  import NamespaceIcon from './NamespaceIcon.svelte';
  import type { NamespaceManagementState } from './namespace-management-state.svelte';

  let { state }: { state: NamespaceManagementState } = $props();
  const id = $props.id();
</script>

<section class="namespaces" aria-labelledby={id + '-title'}>
  <h3 id={id + '-title'}>Shared namespaces</h3>
  <DelayedSpinner active={state.busy} label="Updating namespaces" />
  {#if state.error || state.needsReload}
    <div>
      {#if state.error}<p role="alert">{state.error}</p>{/if}
      <Button variant="secondary" disabled={!state.canOpenEditor} onclick={state.requestReload}>Reload namespaces</Button>
    </div>
  {/if}
  {#if state.selectedGroupId === null}<p class="empty">Select a group to assign access.</p>{/if}
  <ul aria-label="Shared namespaces" role="list" aria-busy={state.busy}>
    {#each state.namespaces as namespace (namespace.id)}
      <AdminPermissionRow name={namespace.name} description={namespace.description}>
        {#snippet icon()}<NamespaceIcon />{/snippet}
        {#snippet actions()}
          {#if state.selectedGroupId !== null}
            <SegmentedRadio size="compact" label="Access" accessibleName={'Access to ' + namespace.name} options={state.accessOptions} value={state.access(namespace.id)} disabled={!state.canAssignAccess} onchange={(access) => state.stageAccess(namespace.id, access)} />
          {/if}
        {/snippet}
      </AdminPermissionRow>
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
</section>

<form class="permission-save" onsubmit={(event) => { event.preventDefault(); void state.savePermissions(); }}>
  <AdminSaveAction label="Save permissions" loadingLabel="Saving permissions..." loading={state.savingPermissions} disabled={!state.canSavePermissions} message={state.permissionFeedback.message} tone={state.permissionFeedback.tone} icon={state.permissionFeedback.icon} />
</form>

<style>
  .namespaces { display: grid; gap: 1rem; }
  h3 { font-size: 0.9375rem; margin: 0; }
  ul { list-style: none; margin: 0; padding: 0; }
  li.empty { border-top: 1px solid var(--admin-border); padding: 1rem 0; }
  .reload-warning { background: var(--admin-warning-bg); border: 1px solid var(--admin-warning-border); border-radius: var(--admin-radius); color: var(--admin-warning-text); padding: 1rem; }
  .empty { color: var(--admin-muted); font-size: 0.875rem; margin: 0; }
  p[role='alert'] { color: var(--admin-danger-text); }
</style>
