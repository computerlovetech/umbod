<script lang="ts">
  import { permissions, permissionLabels } from '$lib/admin/filesystem/domain/schemas';
  import FilesystemConfirmationDialog from './FilesystemConfirmationDialog.svelte';
  import type { FilesystemAccessState } from './filesystem-access-state.svelte';
  let { state }: { state: FilesystemAccessState } = $props();
</script>

<div class="admin-page filesystem-page">
  <header class="page-heading">
    <div>
      <p class="admin-eyebrow">Administration</p>
      <h1 class="admin-title">Filesystem access</h1>
    </div>
    <span class="scope-badge">Root only</span>
  </header>

  {#if state.loading}<p role="status" class="notice">Loading access…</p>{/if}
  {#if state.error}<p role="alert" class="notice error">{state.error}</p>{/if}
  {#if state.success}<p role="status" class="notice success">{state.success}</p>{/if}

  {#if state.saved}
    {#if state.saved.status === 'conflict'}
      <p role="alert" class="notice error">Root policy conflict. Ask an operator to resolve it, then reload.</p>
    {/if}

    <section class="access-panel" aria-labelledby="group-access-title">
      <header class="section-heading">
        <div class="section-title">
          <h2 id="group-access-title">Groups</h2>
          <span class="count">{state.rows.length}</span>
          {#if state.saved.status === 'uninitialized'}<span class="setup-badge">Not set up</span>{/if}
        </div>
        {#if state.rows.length > 0}
          <button class="secondary compact" type="button" disabled={!state.editable} onclick={state.add}><span aria-hidden="true">+</span> Add group</button>
        {/if}
      </header>

      <fieldset disabled={!state.editable} class="group-list">
        <legend class="visually-hidden">Root group access</legend>
        {#each state.rows as row, index (row.id)}
          <section class="group-card" aria-label={'Group access ' + (index + 1)}>
            <header class="group-heading">
              <h3>Group {index + 1}</h3>
              <button type="button" class="remove" aria-label="Remove group" onclick={() => state.remove(row.id)}>Remove</button>
            </header>
            <div class="identity-fields">
              <div>
                <label for={'group-' + row.id}>Group ID</label>
                <input id={'group-' + row.id} value={row.group_id} oninput={(event) => state.edit(row.id, 'group_id', event.currentTarget.value)} autocomplete="off" spellcheck="false" placeholder="Exact group ID" />
              </div>
              <div>
                <label for={'issuer-' + row.id}>Identity issuer</label>
                <input id={'issuer-' + row.id} value={row.issuer} oninput={(event) => state.edit(row.id, 'issuer', event.currentTarget.value)} autocomplete="off" spellcheck="false" placeholder="Issuer URL" />
              </div>
            </div>
            <div class="permissions" role="group" aria-label={'Permissions for group ' + (index + 1)}>
              {#each permissions as permission (permission)}
                <label class={['permission', { selected: row.permissions.includes(permission) }]}>
                  <input type="checkbox" checked={row.permissions.includes(permission)} onchange={(event) => state.toggle(row.id, permission, event.currentTarget.checked)} />
                  {permissionLabels[permission]}
                </label>
              {/each}
            </div>
            {#if row.permissions.includes('write') && !row.permissions.includes('discover')}
              <p class="field-hint">Also select Browse root to allow creation.</p>
            {/if}
          </section>
        {/each}
        {#if state.rows.length === 0}
          <div class="empty-state">
            <svg aria-hidden="true" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" /><path d="M3 9h18" /></svg>
            <h3>No groups selected</h3>
            <p>Add a group to grant root access.</p>
            <button class="secondary" type="button" onclick={state.add}><span aria-hidden="true">+</span> Add group</button>
          </div>
        {/if}
      </fieldset>
    </section>

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
  .page-heading, .section-heading, .section-title, .group-heading, .action-bar, .actions { display: flex; align-items: center; }
  .page-heading, .section-heading, .group-heading, .action-bar { justify-content: space-between; gap: 1rem; }
  .admin-title { margin-bottom: 0; }
  .scope-badge, .count, .setup-badge, .read-only { font-size: 0.75rem; font-weight: 500; white-space: nowrap; }
  .scope-badge, .count { background: var(--admin-soft); color: var(--admin-muted); border-radius: 999px; padding: 0.3rem 0.65rem; }
  .scope-badge { border: 1px solid var(--admin-border); }
  .setup-badge, .read-only { color: var(--admin-muted); }
  .section-title { gap: 0.6rem; flex-wrap: wrap; }
  h2, h3, p { margin: 0; }
  h2 { font-size: 1rem; font-weight: 600; }
  h3 { font-size: 0.875rem; font-weight: 600; }
  .access-panel { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); overflow: hidden; }
  .section-heading { padding: 1rem 1.25rem; border-bottom: 1px solid var(--admin-border); min-height: 2.25rem; }
  .group-list { border: 0; padding: 0; margin: 0; min-width: 0; }
  .group-card { padding: 0.75rem 1.25rem 1.25rem; }
  .group-card + .group-card { border-top: 1px solid var(--admin-border); }
  .group-heading { margin-bottom: 0.65rem; }
  .identity-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
  .identity-fields > div { min-width: 0; }
  .identity-fields label { display: block; font-size: 0.8125rem; font-weight: 500; margin-bottom: 0.4rem; }
  input:not([type="checkbox"]) { width: 100%; box-sizing: border-box; padding: 0.65rem 0.75rem; background: var(--admin-panel); color: var(--admin-ink); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); font: inherit; font-size: 0.875rem; }
  input::placeholder { color: var(--admin-muted); }
  .permissions { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 1rem; }
  .permission { display: inline-flex; align-items: center; gap: 0.45rem; padding: 0.5rem 0.65rem; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); font-size: 0.8125rem; cursor: pointer; }
  .permission.selected { background: var(--admin-soft); border-color: var(--admin-accent); }
  input[type="checkbox"] { margin: 0; accent-color: var(--admin-accent); width: 1rem; height: 1rem; }
  .empty-state { display: flex; flex-direction: column; align-items: center; gap: 0.65rem; padding: 2.5rem 1.25rem; text-align: center; }
  .empty-state svg { color: var(--admin-muted); margin-bottom: 0.25rem; }
  .empty-state h3 { font-size: 1rem; }
  .empty-state p { color: var(--admin-muted); font-size: 0.875rem; }
  .empty-state button { margin-top: 0.35rem; }
  button { cursor: pointer; padding: 0.65rem 1rem; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); font: inherit; font-size: 0.875rem; font-weight: 500; }
  .secondary { background: var(--admin-panel); color: var(--admin-ink); }
  .secondary:hover:not(:disabled) { background: var(--admin-soft); }
  .primary { background: var(--admin-accent); color: white; border-color: var(--admin-accent); min-width: 5rem; }
  .primary:hover:not(:disabled) { filter: brightness(0.92); }
  .compact { padding: 0.45rem 0.75rem; }
  .remove { background: transparent; border-color: transparent; color: var(--admin-muted); padding: 0.4rem 0; }
  .remove:hover:not(:disabled) { color: var(--admin-danger-text); }
  button:disabled, fieldset:disabled .permission { cursor: not-allowed; opacity: 0.55; }
  input:focus-visible, button:focus-visible, summary:focus-visible { outline: 3px solid var(--admin-focus); outline-offset: 3px; }
  .field-hint { color: var(--admin-muted); font-size: 0.8125rem; line-height: 1.5; margin-top: 0.75rem; }
  .validation { margin-top: -0.5rem; }
  .access-details { font-size: 0.8125rem; color: var(--admin-muted); }
  summary { cursor: pointer; width: fit-content; padding: 0.25rem 0; color: var(--admin-ink); }
  summary .count, summary .read-only { margin-left: 0.5rem; }
  .access-details p { line-height: 1.6; margin-top: 0.5rem; }
  dl { margin: 0.75rem 0; }
  dl > div { display: flex; flex-wrap: wrap; gap: 0.5rem 1rem; margin: 0.4rem 0; }
  dt { min-width: 7rem; }
  dd { margin: 0; overflow-wrap: anywhere; }
  .recursive-grants li { display: flex; flex-direction: column; gap: 0.3rem; overflow-wrap: anywhere; margin-top: 1rem; }
  .notice { padding: 0.75rem 1rem; background: var(--admin-soft); border-radius: var(--admin-radius); font-size: 0.875rem; line-height: 1.5; }
  .error { color: var(--admin-danger-text); }
  .success { color: var(--admin-accent); }
  .action-bar { position: sticky; bottom: 0; background: var(--admin-panel); padding: 1rem 0; border-top: 1px solid var(--admin-border); z-index: 1; }
  .actions { gap: 0.65rem; margin-left: auto; }
  .draft-status { color: var(--admin-muted); font-size: 0.8125rem; display: flex; align-items: center; gap: 0.5rem; }
  .dirty-dot { width: 0.4rem; height: 0.4rem; border-radius: 50%; background: var(--admin-accent); flex-shrink: 0; }
  .visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0; }
  @media (max-width: 640px) {
    .identity-fields { grid-template-columns: 1fr; gap: 0.75rem; }
    .page-heading { align-items: flex-start; }
    .scope-badge { margin-top: 0.25rem; }
    .section-heading { padding: 1rem; }
    .group-card { padding: 0.75rem 1rem 1rem; }
    .action-bar { flex-wrap: wrap; gap: 0.75rem; }
    .draft-status { flex-basis: 100%; }
    .actions { width: 100%; }
    .actions button { flex: 1; }
  }
</style>
