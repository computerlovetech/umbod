<script lang="ts">
  import { permissions, permissionLabels } from '$lib/admin/filesystem/domain/schemas';
  import FilesystemConfirmationDialog from './FilesystemConfirmationDialog.svelte';
  import AdminSplitWorkspace from '$lib/components/admin/shared/AdminSplitWorkspace.svelte';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import GroupPermissionsTabs from '$lib/components/admin/group-permissions/GroupPermissionsTabs.svelte';
  import FilesystemGroupDialog from './FilesystemGroupDialog.svelte';
  import { FilesystemGroupEditorState } from './filesystem-group-editor-state.svelte';
  import type { FilesystemAccessState } from './filesystem-access-state.svelte';
  let { state }: { state: FilesystemAccessState } = $props();
  const editor = new FilesystemGroupEditorState(() => state);
</script>

<div class="admin-page filesystem-page">
  <header class="page-heading">
    <div>
      <p class="admin-eyebrow">Administration</p>
      <h1 class="admin-title">Group permissions</h1>
      <p class="admin-lede">Add groups and see what each group’s agents can do — which filesystem permissions they have at the root.</p>
    </div>
    <Button disabled={!state.editable} onclick={editor.openAdd}><span class="plus" aria-hidden="true">+</span> Add Group</Button>
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
    <AdminSplitWorkspace ariaLabel="Filesystem access workspace" sidebarLabel="Groups" sidebarHeading="Groups" count={state.rows.length} detailLabel="Group access overview">
      {#snippet sidebar()}
        <ul class="groups">
          {#each state.rows as row (row.id)}
            <li>
              <button class={['group-button', { selected: editor.selected?.id === row.id }]} type="button" aria-current={editor.selected?.id === row.id ? 'true' : undefined} onclick={() => editor.select(row.id)}>
                <span class="avatar">{(row.group_id.trim() || '?').slice(0, 1).toUpperCase()}</span>
                <span>{row.group_id.trim() ? row.group_id : 'Blank group ID (legacy)'}</span>
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
              <h2>{row.group_id.trim() ? row.group_id : 'Blank group ID (legacy)'}</h2>
              <p>Filesystem permission set</p>
            </div>
            <span class="scope-badge">Root only</span>
          </header>
          <p class="description">What agents in this group can do at the filesystem root. Edit the group to change its identity or permissions.</p>
          <div class="stat-card"><strong>{row.permissions.length}<span> / {permissions.length}</span></strong><p>Permissions</p></div>
          <section class="overview-block" aria-labelledby="identity-title">
            <h3 id="identity-title">Group identity</h3>
            <dl>
              <div><dt>Group ID</dt><dd>{row.group_id.trim() ? row.group_id : 'Blank group ID (legacy)'}</dd></div>
              <div><dt>Identity issuer</dt><dd>{row.issuer.trim() ? row.issuer : 'Blank issuer (legacy)'}</dd></div>
            </dl>
          </section>
          <section class="overview-block" aria-labelledby="permissions-title">
            <h3 id="permissions-title">Filesystem &amp; permissions</h3>
            {#if row.permissions.length === 0}<p class="description">No permissions</p>{/if}
            {#each permissions as permission (permission)}
              <div class="permission-row">
                <span>{permissionLabels[permission]}</span>
                <span class={['permission-status', { granted: row.permissions.includes(permission) }]}>{row.permissions.includes(permission) ? 'Allowed' : 'No access'}</span>
              </div>
            {/each}
            {#if row.permissions.includes('write') && !row.permissions.includes('discover')}<p class="field-hint">Also select Browse root to allow creation.</p>{/if}
          </section>
          <div class="detail-actions">
            <Button variant="secondary" disabled={!state.editable} onclick={() => state.remove(row.id)} aria-label="Remove group">Remove group</Button>
            <Button variant="secondary" disabled={!state.editable} onclick={editor.openEdit}>Edit group</Button>
          </div>
        {:else}
          <div class="empty-state">
            <h2>No groups selected</h2>
            <p>Add a group to grant root access.</p>
            <span class="scope-badge">Root only</span>
          </div>
        {/if}
      {/snippet}
    </AdminSplitWorkspace>

    {#if state.rows.length > 0 && state.validationMessage}
      <p role="status" class="field-hint validation">{state.validationMessage}</p>
    {/if}

    {#if state.saved.unmanaged_groups.length > 0}
      <details class="access-details recursive-grants">
        <summary>Recursive grants <span class="count">{state.saved.unmanaged_groups.length}</span><span class="read-only">Read-only</span></summary>
        <ul>{#each state.saved.unmanaged_groups as group (JSON.stringify([group.issuer, group.group_id]))}<li><strong>{group.group_id.trim() ? group.group_id : 'Blank group ID (legacy)'}</strong><span>{group.issuer.trim() ? group.issuer : 'Blank issuer (legacy)'}</span><span>{group.permissions.length ? group.permissions.map((permission) => permissionLabels[permission]).join(', ') : 'No permissions'}</span></li>{/each}</ul>
      </details>
    {/if}

    <details class="access-details">
      <summary>Access details</summary>
      <dl>
        <div><dt>Group claim</dt><dd><code>{state.saved.group_claim || 'Not configured'}</code></dd></div>
        {#if state.saved.suggested_issuer}<div><dt>Configured issuer</dt><dd><code>{state.saved.suggested_issuer}</code></dd></div>{/if}
      </dl>
      <p>Root access only, with no inheritance. New items are private to their creator.</p>
      <p>Requires verified authentication and exact issuer/group IDs. Local or simulated users cannot access the filesystem.</p>
      <p>User grants, recursive grants and child policies are unchanged.</p>
    </details>
  {/if}

  <footer class="action-bar">
    <p role="status" class="draft-status">
      {#if state.dirty}<span class="dirty-dot" aria-hidden="true"></span>Unsaved changes
      {:else if state.saved?.status === 'uninitialized'}Save to finish setup.
      {/if}
    </p>
    <div class="actions">
      <button class="secondary" type="button" disabled={state.busy} onclick={state.requestReload}>{state.dirty ? 'Discard changes' : 'Reload'}</button>
      {#if state.saved}<button class="primary" type="button" disabled={!state.canSave} onclick={state.save}>{state.saving ? 'Saving…' : 'Save'}</button>{/if}
    </div>
  </footer>
</div>

{#if editor.draft}<FilesystemGroupDialog {editor} />{/if}

{#if state.confirmation}
  <FilesystemConfirmationDialog
    title={state.confirmation === 'empty' ? 'Save with no group access?' : 'Discard unsaved changes?'}
    description={state.confirmation === 'empty' ? 'All direct root group grants will be removed. User grants and recursive grants stay unchanged.' : 'Your unsaved changes will be lost.'}
    confirmLabel={state.confirmation === 'empty' ? 'Save empty policy' : 'Discard and reload'}
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
  .scope-badge, .count, .read-only { font-size: 11px; font-weight: 500; white-space: nowrap; }
  .scope-badge, .count { background: var(--admin-soft); border: 1px solid var(--admin-border); color: var(--admin-muted); border-radius: 999px; padding: 4px 9px; }
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
  .stat-card { border: 1px solid var(--admin-border); border-radius: 8px; display: inline-block; min-width: 118px; padding: 10px 15px; margin-bottom: 26px; }
  .stat-card strong { font-size: 20px; }
  .stat-card strong span { color: var(--admin-muted); font-size: 13px; font-weight: 500; }
  .stat-card p { color: var(--admin-muted); font-size: 11px; margin: 1px 0 0; }
  .overview-block { margin-bottom: 24px; }
  h3 { color: var(--admin-muted); font-family: var(--admin-mono); font-size: 12px; font-weight: 500; letter-spacing: 0.5px; margin: 0 0 8px; text-transform: uppercase; }
  .permission-row { align-items: center; border-bottom: 1px solid var(--admin-soft); display: flex; font-size: 13px; gap: 12px; justify-content: space-between; padding: 11px 0; }
  .permission-status { background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: 4px; color: var(--admin-muted); font-size: 11px; font-weight: 600; padding: 2px 7px; }
  .permission-status.granted { background: var(--admin-success-bg); border-color: var(--admin-success-border); color: var(--admin-success-text); }
  .detail-actions, .actions { display: flex; flex-wrap: wrap; gap: 10px; justify-content: flex-end; }
  .empty-state { align-items: center; display: flex; flex-direction: column; gap: 12px; padding: 60px 0; text-align: center; }
  .empty-state p { color: var(--admin-muted); font-size: 13px; margin: 0; }
  button { cursor: pointer; padding: 0.65rem 1rem; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); font: inherit; font-size: 13px; font-weight: 500; }
  .secondary { background: var(--admin-panel); color: var(--admin-ink); }
  .secondary:hover:not(:disabled) { background: var(--admin-soft); }
  .primary { background: var(--admin-action); color: var(--admin-on-action); border-color: var(--admin-action); min-width: 5rem; }
  button:disabled { cursor: not-allowed; opacity: 0.55; }
  button:focus-visible, summary:focus-visible { outline: 3px solid var(--admin-focus); outline-offset: 3px; }
  .field-hint { color: var(--admin-muted); font-size: 13px; line-height: 1.5; margin-top: 12px; }
  .validation { margin-top: -8px; }
  .access-details { font-size: 13px; color: var(--admin-muted); }
  summary { cursor: pointer; width: fit-content; padding: 4px 0; color: var(--admin-ink); }
  summary .count, summary .read-only { margin-left: 8px; }
  .access-details p { line-height: 1.6; margin-top: 8px; }
  dl { font-size: 13px; margin: 12px 0; }
  dl > div { display: flex; flex-wrap: wrap; gap: 8px 16px; margin: 8px 0; }
  dt { color: var(--admin-muted); min-width: 7rem; }
  dd { margin: 0; overflow-wrap: anywhere; min-width: 0; }
  .recursive-grants li { display: flex; flex-direction: column; gap: 5px; overflow-wrap: anywhere; margin-top: 16px; }
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
