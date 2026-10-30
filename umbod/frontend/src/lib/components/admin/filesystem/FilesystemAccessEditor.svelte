<script lang="ts">
  import { permissions, permissionLabels } from '$lib/admin/filesystem/domain/schemas';
  import FilesystemConfirmationDialog from './FilesystemConfirmationDialog.svelte';
  import AdminSaveAction from '$lib/components/admin/shared/AdminSaveAction.svelte';
  import { FilesystemGroupEditorState } from './filesystem-group-editor-state.svelte';
  import type { FilesystemAccessState } from './filesystem-access-state.svelte';
  let { state, editor }: { state: FilesystemAccessState; editor: FilesystemGroupEditorState } = $props();
</script>


  {#if state.loading}<p role="status" class="notice permission-notice">Loading access…</p>{/if}
  {#if state.error}
    <div role="alert" class="notice permission-notice error">
      <p>{state.error}</p>
      {#if !state.saved}<button type="button" onclick={state.ensureLoaded}>Retry</button>
      {:else if state.blocked}<button type="button" onclick={state.requestReload}>Reload policy</button>{/if}
    </div>
  {/if}
  {#if state.success}<p role="status" class="notice permission-notice success">{state.success}</p>{/if}

  {#if state.saved}
    {#if state.saved.status === 'conflict'}
      <div role="alert" class="notice permission-notice error"><p>Root policy conflict. Ask an operator to resolve it, then reload.</p><button type="button" onclick={state.requestReload}>Reload policy</button></div>
    {/if}

    {#if state.saved.status === 'uninitialized'}<p class="notice permission-notice">Not set up</p>{/if}
        {#if editor.selected}
          {@const row = editor.selected}
          {#if editor.assignmentMessage}
            <p class="permission-description" role="status">{editor.assignmentMessage}</p>
          {:else}
          <p class="permission-description">Choose this group’s root permissions. Registration alone grants no access.</p>
          {#if !row.registered}<p class="field-hint">This group is not in the shared group catalogue.</p>{/if}
          {#if row.permissions.length === 0}
            <p class="permission-description">No direct root access. This group has no direct root permissions.</p>
          {/if}
          <section class="permission-block" aria-labelledby="permissions-title">
            <h3 id="permissions-title">Filesystem &amp; permissions</h3>
            <p class="field-hint">Changes are staged across groups until you save permissions.</p>
            {#each permissions as permission (permission)}
              <label class="permission-row">
                <span>{permissionLabels[permission]}</span>
                <input type="checkbox" checked={editor.permissions.includes(permission)} disabled={!editor.editable} onchange={(event) => editor.toggle(permission, event.currentTarget.checked)} />
              </label>
            {/each}
            {#if editor.permissions.includes('write') && !editor.permissions.includes('discover')}<p class="field-hint">Also select Browse root to allow creation.</p>{/if}
            <form class="permission-save" onsubmit={(event) => { event.preventDefault(); void state.save(); }}>
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
        {#if !editor.selected || (editor.assignmentMessage && state.canSave)}
          <form class="permission-save" onsubmit={(event) => { event.preventDefault(); void state.save(); }}>
            <AdminSaveAction label="Save permissions" loadingLabel="Saving…" loading={state.saving} disabled={!state.canSave} message={state.saved?.status === 'uninitialized' ? 'Save to finish setup.' : state.dirty ? 'Unsaved changes' : 'Permissions up to date'} tone={state.dirty ? 'warning' : 'success'} icon={state.dirty ? '•' : '✓'} />
          </form>
        {/if}


    {#if state.rows.length > 0 && state.validationMessage}
      <p role="status" class="field-hint validation">{state.validationMessage}</p>
    {/if}

  {/if}



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
  .scope-badge { font-size: 11px; font-weight: 500; white-space: nowrap; }
  .scope-badge { background: var(--admin-soft); border: 1px solid var(--admin-border); color: var(--admin-muted); border-radius: 999px; padding: 4px 9px; }
  .empty-state h2 { font-size: 22px; font-weight: 600; letter-spacing: -0.03em; margin: 0; overflow-wrap: anywhere; }
  .permission-row { align-items: center; border-bottom: 1px solid var(--admin-soft); display: flex; font-size: 13px; gap: 12px; justify-content: space-between; padding: 11px 0; }
  input[type="checkbox"] { accent-color: var(--admin-accent); height: 16px; width: 16px; }
  input:focus-visible { outline: 3px solid var(--admin-focus); outline-offset: 3px; }
  .empty-state { align-items: center; display: flex; flex-direction: column; gap: 12px; padding: 60px 0; text-align: center; }
  .empty-state p { color: var(--admin-muted); font-size: 13px; margin: 0; }
  .field-hint { color: var(--admin-muted); font-size: 13px; line-height: 1.55; margin: 12px 0; }
  .validation { margin: 12px 0 0; }
  .notice { padding: 12px 16px; background: var(--admin-soft); border-radius: var(--admin-radius); font-size: 13px; line-height: 1.5; }
  .notice p { margin: 0 0 12px; }
  .error { color: var(--admin-danger-text); }
  .success { color: var(--admin-accent); }
</style>
