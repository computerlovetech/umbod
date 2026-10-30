<script lang="ts">
  import type { GroupsState } from './groups-state.svelte';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import GroupFormModal from './GroupFormModal.svelte';
  let { state }: { state: GroupsState } = $props();
</script>

<section aria-labelledby="groups-title" class="groups-page">
  <header>
    <div>
      <h1 id="groups-title" class="admin-title">Groups</h1>
      <p class="admin-lede">Manage shared group labels and descriptions. Registration grants no access and does not change identity provider membership.</p>
    </div>
    {#if !state.denied}<Button disabled={state.pending} onclick={state.create}>Add Group</Button>{/if}
  </header>
  <a href="/admin/group-permissions/connectors">Assign group permissions</a>
  {#if state.error && !state.formOpen}<p role="alert">{state.error}</p>{/if}
  {#if state.message && !state.formOpen}<p role="status">{state.message}</p>{/if}
  {#if !state.denied}
    <label for="group-search">Search groups</label>
    <input id="group-search" type="search" value={state.query} oninput={(event) => state.setQuery(event.currentTarget.value)} />
    <ul>
      {#each state.filteredGroups as group (group.group_id)}
        <li>
          <div><h2>{group.label}</h2><p>{group.description}</p><p>Provider group ID: <code>{group.group_id}</code></p></div>
          <div class="actions">
            <Button variant="secondary" disabled={state.pending} aria-label={`Edit ${group.label}`} onclick={() => state.edit(group)}>Edit</Button>
            <Button variant="danger" disabled={state.pending} aria-label={`Delete ${group.label}`} onclick={() => state.requestDelete(group.group_id)}>Delete</Button>
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
  header, li, .actions { display: flex; gap: 16px; justify-content: space-between; align-items: center; flex-wrap: wrap; }
  ul { list-style: none; margin: 0; padding: 0; }
  li, section section { padding: 20px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); margin-bottom: 12px; }
  h2 { margin: 0; font-size: 18px; }
  p, code { overflow-wrap: anywhere; white-space: pre-wrap; }
  p { color: var(--admin-muted); }
  input { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: 6px; padding: 10px; color: var(--admin-ink); font: inherit; min-width: 0; }
  input:focus-visible { outline: 2px solid var(--admin-focus); }
</style>
