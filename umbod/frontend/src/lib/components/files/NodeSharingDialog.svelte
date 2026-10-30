<script lang="ts">
  import { nativeDialog } from '$lib/components/shared/dialogs/native-dialog';
  import Form from '$lib/components/admin/shared/Form.svelte';
  import LoadingButton from '$lib/components/admin/shared/LoadingButton.svelte';
  import Select from '$lib/components/admin/shared/Select.svelte';
  import type { SharingDialogState } from '$lib/files/state/sharing-dialog-state.svelte';

  let { state, signIn }: { state: SharingDialogState; signIn: () => void } = $props();
  const id = $props.id();

  function backdrop(event: MouseEvent): void {
    if (event.target !== event.currentTarget) return;
    const bounds = (event.currentTarget as HTMLDialogElement).getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) void state.close();
  }

  function submit(event: SubmitEvent): void { event.preventDefault(); void state.save(); }
</script>

<dialog aria-labelledby={id + '-title'} aria-modal="true" onclick={backdrop} {@attach nativeDialog(() => { void state.close(); }, () => !state.pending, '[data-dialog-cancel]')}>
  <header>
    <h2 id={id + '-title'}>Share “{state.node?.name || 'Files'}”</h2>
    <button class="close" type="button" aria-label="Close sharing" data-dialog-cancel disabled={state.pending} onclick={() => { void state.close(); }}>
      <svg aria-hidden="true" focusable="false" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="m6 6 12 12M18 6 6 18" /></svg>
    </button>
  </header>
  {#snippet fields()}
    {#if state.phase === 'loading'}
      <p role="status">Loading sharing and registered groups…</p>
    {:else if state.phase === 'ready'}
      <fieldset disabled={!state.editable}>
        <legend class="visually-hidden">Group access</legend>
        <div class="recipient-picker">
          <Select
            id={id + '-group'}
            label="Add group"
            value=""
            options={state.groupOptions}
            disabled={!state.editable || state.groupsLoading}
            search={{ value: state.filter, oninput: state.changeFilter, placeholder: 'Search groups by name or ID' }}
            emptyMessage="No groups found"
            onchange={state.add}
          />
          {#if state.groupsLoading}<p role="status">Refreshing groups…</p>{/if}
        </div>
        {#each state.groups as group (group.group_id)}
          <section class="group" aria-label={group.label}>
            <div class="group-heading"><div><h3>{group.label}</h3>{#if group.label !== group.group_id}<p class="provider-id">{group.group_id}</p>{/if}{#if group.description}<p class="hint">{group.description}</p>{/if}</div><button type="button" class="remove" aria-label={`Remove ${group.label}`} onclick={() => state.remove(group.group_id)}>Remove</button></div>
            <div class="permissions">
              {#each state.permissions as permission (permission.value)}
                <label class="permission"><input type="checkbox" checked={group.permissions.includes(permission.value)} onchange={(event) => state.changePermission(group.group_id, permission.value, event.currentTarget.checked)} />{permission.label}</label>
              {/each}
            </div>
            {#if group.permissions.length === 0}<p class="error" role="alert">Choose at least one permission or remove this group.</p>{/if}
          </section>
        {/each}
      </fieldset>
    {/if}
    {#if state.error}<p class="error" role="alert">{state.error}</p>{/if}
    {#if state.groupsError}<p class="error" role="alert">{state.groupsError}</p>{/if}
    {#if state.needsGroupsRefresh || state.groupsError}<LoadingButton label="Refresh registered groups" loading={state.groupsLoading} variant="secondary" disabled={!state.editable} onclick={state.refreshGroups} />{/if}
    {#if state.needsReload || state.phase === 'error'}<LoadingButton label="Reload latest access" loading={false} variant="secondary" disabled={state.pending} onclick={state.reloadLatest} />{/if}
    {#if state.phase === 'sign-in'}<LoadingButton label="Sign in" loading={false} variant="secondary" onclick={signIn} />{/if}
  {/snippet}
  {#snippet actions()}
    <LoadingButton label="Cancel" loading={false} disabled={state.pending} variant="secondary" onclick={() => { void state.close(); }} />
    <LoadingButton type="submit" label="Save sharing" loadingLabel="Saving…" loading={state.pending} disabled={!state.canSave} />
  {/snippet}
  <Form aria-label="Manage group sharing" onsubmit={submit} {fields} {actions} />
</dialog>

<style>
  dialog { box-sizing: border-box; width: min(42rem, calc(100% - 2rem)); max-width: none; max-height: calc(100dvh - 2rem); overflow: hidden; padding: 1.25rem; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-panel); color: var(--admin-ink); box-shadow: var(--admin-shadow-dialog); }
  dialog[open] { display: flex; flex-direction: column; }
  dialog::backdrop { background: var(--admin-overlay); }
  header { display: flex; align-items: start; justify-content: space-between; gap: 1rem; flex: none; }
  h2 { font-size: 1.05rem; margin: 0 0 0.35rem; overflow-wrap: anywhere; }
  h3 { font-size: 0.95rem; margin: 0; overflow-wrap: anywhere; }
  p { margin: 0; line-height: 1.5; }
  .hint, .provider-id { font-size: 0.85rem; color: var(--admin-muted); }
  fieldset { display: grid; gap: 1rem; min-width: 0; border: 0; margin: 0; padding: 0; }
  .recipient-picker { display: grid; gap: 0.5rem; }
  .group { padding: 1rem; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); }
  .group-heading { display: flex; align-items: start; justify-content: space-between; gap: 0.75rem; }
  .group-heading > div { min-width: 0; }
  .provider-id { white-space: pre-wrap; overflow-wrap: anywhere; }
  .permissions { display: flex; flex-wrap: wrap; gap: 0.75rem 1rem; margin-top: 0.85rem; }
  .permission { display: inline-flex; align-items: center; gap: 0.4rem; font-size: 0.85rem; }
  input[type='checkbox'] { accent-color: var(--admin-accent); width: 1rem; height: 1rem; }
  .close, .remove { border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-panel); color: var(--admin-ink); cursor: pointer; font: inherit; }
  .close { display: grid; place-items: center; flex: none; width: 2rem; height: 2rem; padding: 0; }
  .remove { font-size: 0.8rem; padding: 0.4rem 0.6rem; }
  button:disabled { opacity: 0.6; cursor: default; }
  .error { padding: 0.65rem; border-radius: var(--admin-radius); background: var(--admin-danger-bg); color: var(--admin-danger-text); font-size: 0.85rem; }
  :focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
  .visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
  @media (max-width: 480px) { dialog { padding: 1rem; } .group { padding: 0.75rem; } }
</style>
