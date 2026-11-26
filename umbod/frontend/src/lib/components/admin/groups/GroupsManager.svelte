<script lang="ts">
  import type { GroupsState } from './groups-state.svelte';
  import AdminRecordList from '#lib/components/admin/shared/AdminRecordList.svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import PlusIcon from '#lib/components/shared/PlusIcon.svelte';
  import SubpageContainer from '#lib/components/shared/workspace/SubpageContainer.svelte';
  import GroupFormModal from './GroupFormModal.svelte';
  let { state }: { state: GroupsState } = $props();
</script>

<SubpageContainer title="Groups" headingId="groups-title" lede="Manage shared group labels and descriptions. Registration grants no access and does not change identity provider membership.">
  {#snippet navigation()}{/snippet}
  {#snippet actions()}
    {#if !state.denied}<Button disabled={state.pending} onclick={state.create}><PlusIcon />Add Group</Button>{/if}
  {/snippet}
  {#snippet children()}
  <section aria-labelledby="groups-title" class="groups-page">
  {#if state.error && !state.formOpen}<p role="alert">{state.error}</p>{/if}
  {#if state.message && !state.formOpen}<p role="status">{state.message}</p>{/if}
  {#if !state.denied}
    <AdminRecordList items={state.groups} keyOf={(group) => group.group_id} label="Groups" recordHeading="Group" detailHeading="Provider group ID" emptyMessage="No groups yet.">
      {#snippet identity(group)}
        <div class="group-identity">
          <span class="group-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" focusable="false">
              <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
              <circle cx="9" cy="7" r="4" />
            </svg>
          </span>
          <div>
            <h2>{group.label}</h2>
            {#if group.description}<p class="group-description">{group.description}</p>{/if}
            <a class="permissions-link" href={'/admin/group-permissions/connectors?group=' + encodeURIComponent(group.group_id)} aria-label={'View permissions for ' + group.label}>View permissions</a>
          </div>
        </div>
      {/snippet}
      {#snippet detail(group)}
        <div class="group-provider"><span>Provider group ID</span><code>{group.group_id}</code></div>
      {/snippet}
      {#snippet actions(group)}
        <Button variant="secondary" iconOnly disabled={state.pending} aria-label={`Edit ${group.label}`} title={`Edit ${group.label}`} onclick={() => state.edit(group)}>
          <svg aria-hidden="true" focusable="false" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="m15 4 5 5M4 20l5-1L21 7a2.1 2.1 0 0 0-5-5L4 14zM4 20h16" /></svg>
        </Button>
        <Button variant="danger" iconOnly disabled={state.pending} aria-label={`Delete ${group.label}`} title={`Delete ${group.label}`} onclick={() => state.requestDelete(group.group_id)}>
          <svg aria-hidden="true" focusable="false" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M9 6V4h6v2M5 6l1 14h12l1-14M10 10v6M14 10v6" /></svg>
        </Button>
      {/snippet}
    </AdminRecordList>
    {#if state.formOpen}<GroupFormModal {state} />{/if}
    {#if state.deleting !== null}
      <section aria-label="Confirm group deletion">
        <h2>Delete group?</h2>
        <p>Delete provider group ID <code>{state.deleting}</code>? Deletion is blocked while connector, capability or filesystem references remain.</p>
        <div class="actions">
          <Button variant="danger" disabled={state.pending} onclick={state.delete}>{state.pending ? 'Deleting…' : 'Confirm delete'}</Button>
          <Button variant="secondary" disabled={state.pending} onclick={state.cancel}>Cancel</Button>
        </div>
      </section>
    {/if}
  {/if}
  </section>
  {/snippet}
</SubpageContainer>

<style>
  .groups-page { display: grid; gap: 16px; }
  .group-identity { align-items: center; display: flex; gap: .75rem; }
  .group-identity > div { min-width: 0; }
  .group-icon { background: var(--admin-soft); border-radius: var(--admin-radius); color: var(--admin-muted); display: grid; flex: none; height: 2.25rem; place-items: center; width: 2.25rem; }
  .group-icon svg { display: block; height: 1.125rem; width: 1.125rem; }
  .actions { display: flex; align-items: center; gap: 8px; flex-wrap: nowrap; }
  .permissions-link { color: var(--admin-muted); display: inline-block; font-size: .8125rem; margin-top: .25rem; }
  .group-description { margin: 4px 0 0; font-size: 14px; }
  .group-provider { display: grid; gap: 4px; font-size: 13px; }
  .group-provider span { color: var(--admin-muted); }
  section section { padding: 20px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); }
  h2 { margin: 0; font-size: 15px; }
  p, code { overflow-wrap: anywhere; white-space: pre-wrap; }
  p { color: var(--admin-muted); }
</style>
