<script lang="ts">
  import { permissions, permissionLabels } from '$lib/admin/filesystem/domain/schemas';
  import FilesystemConfirmationDialog from './FilesystemConfirmationDialog.svelte';
  import AdminSplitWorkspace from '$lib/components/admin/shared/AdminSplitWorkspace.svelte';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import AdminSaveAction from '$lib/components/admin/shared/AdminSaveAction.svelte';
  import GroupPermissionsTabs from '$lib/components/admin/group-permissions/GroupPermissionsTabs.svelte';
  import GroupRegistrationDialog from '../group-permissions/shared/GroupRegistrationDialog.svelte';
  import { GroupRegistrationState } from '../group-permissions/shared/group-registration-state.svelte';
  import { FilesystemGroupEditorState } from './filesystem-group-editor-state.svelte';
  import type { FilesystemAccessState } from './filesystem-access-state.svelte';
  let { state }: { state: FilesystemAccessState } = $props();
  const editor = new FilesystemGroupEditorState(() => state);
  const registration = new GroupRegistrationState((groupId) => state.registerGroup(groupId), editor.select);
</script>

<div class="admin-page filesystem-page">
  <header class="page-heading">
    <div>
      <p class="admin-eyebrow">Administration</p>
      <h1 class="admin-title">Group permissions</h1>
      <p class="admin-lede">Register shared groups, then assign filesystem access separately.</p>
    </div>
    <Button disabled={state.busy || registration.pending} onclick={registration.show}><span class="plus" aria-hidden="true">+</span> Add Group</Button>
  </header>

  <GroupPermissionsTabs activeTab="filesystem" />

  {#if state.loading}<p role="status" class="notice">Loading access…</p>{/if}
  {#if state.error}<p role="alert" class="notice error">{state.error}</p>{/if}
  {#if state.success}<p role="status" class="notice success">{state.success}</p>{/if}

  {#if state.saved}
    {#if state.saved.status === 'conflict'}
      <p role="alert" class="notice error">Root policy conflict. Ask an operator to resolve it, then reload.</p>
    {/if}

    {#if state.saved.status === 'uninitialized'}<p class="notice">Not set up</p>{/if}
    <AdminSplitWorkspace ariaLabel="Filesystem access workspace" sidebarLabel="Groups" sidebarHeading="Groups" count={state.groupEntries.length} detailLabel="Group access overview">
      {#snippet sidebar()}
        <ul class="groups">
          {#each state.groupEntries as row (row.id)}
            <li>
              <button class={['group-button', { selected: editor.selected?.id === row.id }]} type="button" aria-current={editor.selected?.id === row.id ? 'true' : undefined} onclick={() => editor.select(row.id)}>
                <span class="avatar">{(row.group_id.trim() || '?').slice(0, 1).toUpperCase()}</span>
                <span>{row.group_id}</span>
              </button>
            </li>
          {/each}
        </ul>
      {/snippet}
      {#snippet detail()}
        {#if editor.selected}
          {@const row = editor.selected}
          <header class="detail-heading">
            <span class="avatar large">{(row.group_id.trim() || '?').slice(0, 1).toUpperCase()}</span>
            <div>
              <h2>{row.group_id}</h2>
              <p>Filesystem permission set</p>
            </div>
            <span class="scope-badge">Root only</span>
          </header>
          {#if editor.assignmentMessage}
            <p class="description" role="status">{editor.assignmentMessage}</p>
          {:else}
          <p class="description">Choose this group’s root permissions. Registration alone grants no access.</p>
          {#if !row.registered}<p class="field-hint">This group is not in the shared group catalogue.</p>{/if}
          {#if row.permissions.length === 0}
            <p class="description">No direct root access. This group has no direct root permissions.</p>
          {/if}
          <section class="overview-block" aria-labelledby="permissions-title">
            <h3 id="permissions-title">Filesystem &amp; permissions</h3>
            <p class="field-hint">Changes are staged across groups until you save permissions.</p>
            {#each permissions as permission (permission)}
              <label class="permission-row">
                <span>{permissionLabels[permission]}</span>
                <input type="checkbox" checked={editor.permissions.includes(permission)} disabled={!editor.editable} onchange={(event) => editor.toggle(permission, event.currentTarget.checked)} />
              </label>
            {/each}
            {#if editor.permissions.includes('write') && !editor.permissions.includes('discover')}<p class="field-hint">Also select Browse root to allow creation.</p>{/if}
            <form class="detail-actions" onsubmit={(event) => { event.preventDefault(); void state.save(); }}>
              <AdminSaveAction label="Save permissions" loadingLabel="Saving…" loading={state.saving} disabled={!state.canSave} message={state.error || (state.dirty ? 'Unsaved changes' : 'Permissions up to date')} tone={state.error ? 'error' : state.saving ? 'saving' : state.dirty ? 'warning' : 'success'} icon={state.error ? '!' : state.dirty ? '•' : '✓'} />
            </form>
          </section>
          {/if}
        {:else}
          <div class="empty-state">
            <h2>No groups selected</h2>
            <p>Register a group, then assign root access separately.</p>
            <span class="scope-badge">Root only</span>
          </div>
        {/if}
      {/snippet}
    </AdminSplitWorkspace>

    {#if state.rows.length > 0 && state.validationMessage}
      <p role="status" class="field-hint validation">{state.validationMessage}</p>
    {/if}

    <p class="field-hint">Root permissions apply here only. New items are private to their creator. Other access rules remain unchanged.</p>
  {/if}

  <footer class="action-bar">
    <p role="status" class="draft-status">
      {#if state.dirty}<span class="dirty-dot" aria-hidden="true"></span>Unsaved changes
      {:else if state.saved?.status === 'uninitialized'}Save to finish setup.
      {/if}
    </p>
    <div class="actions">
      <button class="secondary" type="button" disabled={state.busy} onclick={state.requestReload}>{state.dirty ? 'Discard changes' : 'Reload'}</button>
      {#if state.saved && (!editor.selected || (editor.assignmentMessage && state.canSave))}<button class="primary" type="button" disabled={!state.canSave} onclick={state.save}>{state.saving ? 'Saving…' : 'Save permissions'}</button>{/if}
    </div>
  </footer>
</div>

{#if registration.open}<GroupRegistrationDialog {registration} />{/if}

{#if state.confirmation}
  <FilesystemConfirmationDialog
    title={state.confirmation === 'empty' ? 'Clear configurable group permissions?' : 'Discard unsaved changes?'}
    description={state.confirmation === 'empty' ? 'Configurable group permissions will be cleared. Other access rules remain unchanged.' : 'Your unsaved changes will be lost.'}
    confirmLabel={state.confirmation === 'empty' ? 'Clear group permissions' : 'Discard and reload'}
    oncancel={state.cancelConfirmation}
    onconfirm={state.confirm}
  />
{/if}

<style>
  .filesystem-page { display: flex; flex-direction: column; gap: 1.25rem; }
  .page-heading { align-items: flex-start; display: flex; gap: 24px; justify-content: space-between; margin-bottom: 12px; }
  .page-heading :global(.admin-shared-button) { flex-shrink: 0; margin-top: 26px; }
  .plus { font-size: 18px; font-weight: 400; margin-right: 8px; }
  .admin-title { margin-bottom: 0; }
  .scope-badge { font-size: 11px; font-weight: 500; white-space: nowrap; }
  .scope-badge { background: var(--admin-soft); border: 1px solid var(--admin-border); color: var(--admin-muted); border-radius: 999px; padding: 4px 9px; }
  .groups { list-style: none; margin: 0; padding: 0; }
  .group-button { align-items: center; background: transparent; border: 0; border-top: 1px solid var(--admin-border); border-radius: 0; color: var(--admin-ink); display: flex; font-size: 13px; font-weight: 600; gap: 11px; padding: 11px 15px; text-align: left; width: 100%; }
  .group-button > span:last-child { min-width: 0; overflow-wrap: anywhere; }
  .group-button:hover { background: var(--admin-hover); }
  .group-button.selected { background: var(--admin-accent-soft); box-shadow: inset 3px 0 0 var(--admin-accent); }
  .avatar { align-items: center; background: var(--admin-ink); border-radius: 50%; color: var(--admin-on-action); display: inline-flex; flex-shrink: 0; font-size: 11px; font-weight: 700; height: 26px; justify-content: center; width: 26px; }
  .avatar.large { font-size: 15px; height: 38px; width: 38px; }
  .detail-heading { align-items: flex-start; display: flex; gap: 12px; margin-bottom: 8px; }
  .detail-heading > div { flex: 1; min-width: 0; }
  h2 { font-size: 22px; font-weight: 600; letter-spacing: -0.03em; margin: 0; overflow-wrap: anywhere; }
  .detail-heading p, .description { color: var(--admin-muted); font-size: 13px; line-height: 1.55; margin: 0; }
  .description { margin-bottom: 18px; }
  .overview-block { margin-bottom: 24px; }
  h3 { color: var(--admin-muted); font-family: var(--admin-mono); font-size: 12px; font-weight: 500; letter-spacing: 0.5px; margin: 0 0 8px; text-transform: uppercase; }
  .permission-row { align-items: center; border-bottom: 1px solid var(--admin-soft); display: flex; font-size: 13px; gap: 12px; justify-content: space-between; padding: 11px 0; }
  input[type="checkbox"] { accent-color: var(--admin-accent); height: 16px; width: 16px; }
  input:focus-visible { outline: 3px solid var(--admin-focus); outline-offset: 3px; }
  .detail-actions, .actions { display: flex; flex-wrap: wrap; gap: 10px; justify-content: flex-end; }
  .empty-state { align-items: center; display: flex; flex-direction: column; gap: 12px; padding: 60px 0; text-align: center; }
  .empty-state p { color: var(--admin-muted); font-size: 13px; margin: 0; }
  button { cursor: pointer; padding: 0.65rem 1rem; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); font: inherit; font-size: 13px; font-weight: 500; }
  .secondary { background: var(--admin-panel); color: var(--admin-ink); }
  .secondary:hover:not(:disabled) { background: var(--admin-soft); }
  .primary { background: var(--admin-action); color: var(--admin-on-action); border-color: var(--admin-action); min-width: 5rem; }
  button:disabled { cursor: not-allowed; opacity: 0.55; }
  button:focus-visible { outline: 3px solid var(--admin-focus); outline-offset: 3px; }
  .field-hint { color: var(--admin-muted); font-size: 13px; line-height: 1.5; margin-top: 12px; }
  .validation { margin-top: -8px; }
  .notice { padding: 12px 16px; background: var(--admin-soft); border-radius: var(--admin-radius); font-size: 13px; line-height: 1.5; margin: 0; }
  .error { color: var(--admin-danger-text); }
  .success { color: var(--admin-accent); }
  .action-bar { align-items: center; display: flex; justify-content: space-between; gap: 16px; position: sticky; bottom: 0; background: var(--admin-panel); padding: 16px 0; border-top: 1px solid var(--admin-border); z-index: 1; }
  .actions { margin-left: auto; }
  .draft-status { color: var(--admin-muted); font-size: 13px; display: flex; align-items: center; gap: 8px; }
  .dirty-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--admin-accent); flex-shrink: 0; }
  @media (max-width: 1000px) {
    .page-heading { flex-wrap: wrap; gap: 16px; }
    .page-heading :global(.admin-shared-button) { margin-top: 0; }
  }
  @media (max-width: 640px) {
    .detail-heading { flex-wrap: wrap; }
    .action-bar { flex-wrap: wrap; gap: 12px; }
    .draft-status { flex-basis: 100%; }
    .actions { width: 100%; }
    .actions button { flex: 1; }
  }
</style>
