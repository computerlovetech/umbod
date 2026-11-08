<script lang="ts">
  import type { GroupsState } from './groups-state.svelte';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import ButtonLink from '$lib/components/admin/shared/ButtonLink.svelte';
  import GroupFormModal from './GroupFormModal.svelte';
  let { state }: { state: GroupsState } = $props();
</script>

<section aria-labelledby="groups-title" class="groups-page">
  <header>
    <div>
      <h1 id="groups-title" class="admin-title">Groups</h1>
      <p class="admin-lede">Manage shared group labels and descriptions. Registration grants no access and does not change identity provider membership.</p>
    </div>
    <div class="header-actions">
      <ButtonLink variant="secondary" href="/admin/group-permissions/connectors">Assign group permissions</ButtonLink>
      {#if !state.denied}<Button disabled={state.pending} onclick={state.create}>Add Group</Button>{/if}
    </div>
  </header>
  {#if state.error && !state.formOpen}<p role="alert">{state.error}</p>{/if}
  {#if state.message && !state.formOpen}<p role="status">{state.message}</p>{/if}
  {#if !state.denied}
    <div class="search-field">
      <label for="group-search">Search groups</label>
      <input id="group-search" type="search" placeholder="Search groups…" value={state.query} oninput={(event) => state.setQuery(event.currentTarget.value)} />
    </div>
    <ul aria-label="Groups">
      {#each state.filteredGroups as group (group.group_id)}
        <li>
          <div class="group-identity">
            <h2>{group.label}</h2>
            {#if group.description}<p class="group-description">{group.description}</p>{/if}
          </div>
          <div class="group-provider"><span>Provider group ID</span><code>{group.group_id}</code></div>
          <div class="actions">
            <Button variant="secondary" size="compact" iconOnly disabled={state.pending} aria-label={`Edit ${group.label}`} title={`Edit ${group.label}`} onclick={() => state.edit(group)}>
              <svg aria-hidden="true" focusable="false" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="m15 4 5 5M4 20l5-1L21 7a2.1 2.1 0 0 0-5-5L4 14zM4 20h16" /></svg>
            </Button>
            <Button variant="danger" size="compact" iconOnly disabled={state.pending} aria-label={`Delete ${group.label}`} title={`Delete ${group.label}`} onclick={() => state.requestDelete(group.group_id)}>
              <svg aria-hidden="true" focusable="false" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M9 6V4h6v2M5 6l1 14h12l1-14M10 10v6M14 10v6" /></svg>
            </Button>
          </div>
        </li>
      {:else}<li>No matching groups.</li>{/each}
    </ul>
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

<style>
  .groups-page { display: grid; gap: 16px; }
  header, .header-actions, .actions { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
  header { justify-content: space-between; }
  header > div:first-child { flex: 1 1 360px; }
  .header-actions { gap: 8px; }
  .search-field { display: grid; gap: 8px; max-width: 360px; }
  .search-field label { font-size: 13px; font-weight: 600; }
  ul { list-style: none; margin: 0; padding: 0; }
  li { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto; gap: 16px; align-items: center; padding-block: 16px; border-top: 1px solid var(--admin-border); }
  .group-identity, .group-provider { min-width: 0; }
  .group-description { margin: 4px 0 0; font-size: 14px; }
  .group-provider { display: grid; gap: 4px; font-size: 13px; }
  .group-provider span { color: var(--admin-muted); }
  .actions { gap: 8px; flex-wrap: nowrap; }
  section section { padding: 20px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); }
  h2 { margin: 0; font-size: 15px; }
  p, code { overflow-wrap: anywhere; white-space: pre-wrap; }
  p { color: var(--admin-muted); }
  input { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: 6px; padding: 10px; color: var(--admin-ink); font: inherit; min-width: 0; }
  input:focus-visible { outline: 2px solid var(--admin-focus); }
  @media (max-width: 640px) {
    li { grid-template-columns: minmax(0, 1fr) auto; gap: 8px 16px; }
    .group-provider { grid-column: 1; }
    li .actions { grid-column: 2; grid-row: 1 / 3; }
  }
</style>
