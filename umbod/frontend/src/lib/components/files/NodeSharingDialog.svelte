<script lang="ts">
  import Button from '$lib/components/admin/shared/Button.svelte';
  import ModalShell from '$lib/components/shared/ModalShell.svelte';
  import Form from '$lib/components/admin/shared/Form.svelte';
  import LoadingButton from '$lib/components/admin/shared/LoadingButton.svelte';
  import Select from '$lib/components/admin/shared/Select.svelte';
  import type { SharingDialogState } from '$lib/files/state/sharing-dialog-state.svelte';

  let { state, signIn }: { state: SharingDialogState; signIn: () => void } = $props();
  const id = $props.id();

  function submit(event: SubmitEvent): void { event.preventDefault(); void state.save(); }
</script>

  {#snippet fields()}
    {#if state.phase === 'loading'}
      <p role="status">Loading sharing…</p>
    {:else if state.phase === 'ready' || state.refreshing}
      <fieldset class="recipient-types" disabled={state.pending || state.confirmingSwitch || state.refreshing}>
        <legend>Share with</legend>
        <Button type="button" variant={state.recipientType === 'group' ? 'primary' : 'secondary'} aria-pressed={state.recipientType === 'group'} onclick={() => { void state.selectRecipientType('group'); }}>Groups</Button>
        <Button type="button" variant={state.recipientType === 'user' ? 'primary' : 'secondary'} aria-pressed={state.recipientType === 'user'} onclick={() => { void state.selectRecipientType('user'); }}>Users</Button>
      </fieldset>
      {#if state.confirmingSwitch}
        <div class="switch-confirmation" role="group" aria-label="Unsaved sharing changes">
          <p>Discard unsaved changes?</p>
          <Button variant="secondary" type="button" onclick={state.keepEditing}>Keep editing</Button>
          <Button variant="danger" type="button" onclick={() => { void state.discardAndSwitch(); }}>Discard changes</Button>
        </div>
      {/if}
      <fieldset disabled={!state.editable} aria-busy={state.refreshing}>
        <legend class="visually-hidden">Recipient access</legend>
        <div class="recipient-picker">
          <Select
            id={id + '-recipient'}
            label={state.pickerLabel}
            value=""
            options={state.recipientOptions}
            disabled={!state.editable}
            search={{ value: state.filter, oninput: state.changeFilter, placeholder: state.searchPlaceholder }}
            emptyMessage={state.search.emptyMessage}
            onchange={state.add}
          />
          <p class="search-status" role="status">{state.refreshing ? 'Loading sharing…' : state.search.loading ? 'Searching…' : state.search.hasMore ? 'Refine search for more matches.' : ''}</p>
          {#if state.search.error}<p class="error" role="alert">{state.search.error}</p>{#if !state.search.unavailable}<Button type="button" variant="secondary" disabled={!state.editable} onclick={() => { void state.search.refresh(); }}>Retry search</Button>{/if}{/if}
        </div>
        {#each state.recipients as entry (entry.id)}
          <section class="recipient" aria-label={entry.label}>
            <div class="recipient-heading"><div><h3>{entry.label}</h3>{#if entry.label !== entry.id}<p class="provider-id">{entry.id}</p>{/if}</div><Button variant="quiet" size="compact" type="button" aria-label={`Remove ${entry.label}`} onclick={() => state.remove(entry.id)}>Remove</Button></div>
            <div class="permissions">
              {#each state.permissions as permission (permission.value)}
                <label class="permission"><input type="checkbox" checked={entry.permissions.includes(permission.value)} onchange={(event) => state.changePermission(entry.id, permission.value, event.currentTarget.checked)} />{permission.label}</label>
              {/each}
            </div>
            {#if entry.permissions.length === 0}<p class="error" role="alert">Choose at least one permission or remove this recipient.</p>{/if}
          </section>
        {/each}
      </fieldset>
    {/if}
    {#if state.error}<p class="error" role="alert">{state.error}</p>{/if}
    {#if state.needsReload || state.phase === 'error'}<LoadingButton label="Reload latest access" loading={false} variant="secondary" disabled={state.pending} onclick={state.reloadLatest} />{/if}
    {#if state.phase === 'sign-in'}<LoadingButton label="Sign in" loading={false} variant="secondary" onclick={signIn} />{/if}
  {/snippet}
  {#snippet actions()}
    <LoadingButton label="Cancel" loading={false} disabled={state.pending} variant="secondary" data-dialog-cancel onclick={() => { void state.close(); }} />
    <LoadingButton type="submit" label={state.saveLabel} loadingLabel="Saving…" loading={state.pending} disabled={!state.canSave} />
  {/snippet}
<ModalShell title={`Share “${state.nodeName}”`} titleId={id + '-title'} close={() => { void state.close(); }} closeDisabled={state.pending} initialFocus={'button[aria-label="Close"]'} --modal-width="42rem" --modal-padding="1.25rem">
  <Form aria-label="Manage sharing" onsubmit={submit} {fields} {actions} />
</ModalShell>

<style>
  h3 { font-size: 0.95rem; margin: 0; overflow-wrap: anywhere; }
  p { margin: 0; line-height: 1.5; }
  .provider-id { font-size: 0.85rem; color: var(--admin-muted); }
  fieldset { display: grid; gap: 1rem; min-width: 0; border: 0; margin: 0; padding: 0; }
  .recipient-picker { display: grid; gap: 0.5rem; }
  .search-status { min-block-size: 1.5em; font-size: 0.85rem; color: var(--admin-muted); }
  .recipient { padding: 1rem; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); }
  .recipient-heading { display: flex; align-items: start; justify-content: space-between; gap: 0.75rem; }
  .recipient-heading > div { min-width: 0; }
  .provider-id { white-space: pre-wrap; overflow-wrap: anywhere; }
  .permissions { display: flex; flex-wrap: wrap; gap: 0.75rem 1rem; margin-top: 0.85rem; }
  .permission { display: inline-flex; align-items: center; gap: 0.4rem; font-size: 0.85rem; }
  input[type='checkbox'] { accent-color: var(--admin-accent); width: 1rem; height: 1rem; }
  .error { padding: 0.65rem; border-radius: var(--admin-radius); background: var(--admin-danger-bg); color: var(--admin-danger-text); font-size: 0.85rem; }
  :focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
  .visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
  .recipient-types { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1rem; }
  .recipient-types legend { font-size: 0.8125rem; font-weight: 600; margin-bottom: 0.35rem; }
  .switch-confirmation { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; margin-bottom: 1rem; }
  @media (max-width: 480px) { .recipient { padding: 0.75rem; } }
</style>
