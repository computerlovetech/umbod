<script lang="ts">
  import type { CatalogueCapability } from '$lib/dashboard/domain/schemas';
  import { CapabilitiesState, capabilityGroups, capabilityGroupLabels } from '$lib/dashboard/state/capabilities-state.svelte';
  import CapabilityCatalogGrid from '$lib/components/admin/shared/CapabilityCatalogGrid.svelte';
  import ToolDescription from '$lib/components/shared/tools/ToolDescription.svelte';
  import CatalogueToolCard from './CatalogueToolCard.svelte';

  let { capabilities }: { capabilities: readonly CatalogueCapability[] } = $props();
  const state = new CapabilitiesState(() => capabilities);
  const headingId = $props.id();
  const searchId = `${headingId}-search`;
</script>

<section class="capabilities" aria-labelledby={headingId}>
  <h3 id={headingId}>Capabilities</h3>
  <nav aria-label="Connector capabilities">
    {#each capabilityGroups as group (group)}
      <button type="button" class={['capability-tab', { active: state.activeGroup === group }]} aria-pressed={state.activeGroup === group} onclick={() => state.selectGroup(group)}>
        <span>{capabilityGroupLabels[group]}</span>
        <strong>{state.counts[group]}</strong>
      </button>
    {/each}
  </nav>
  <div class="catalogue">
    <div class="catalogue-heading">
      <h4>{capabilityGroupLabels[state.activeGroup]}</h4>
      <p>Available to your account · Read-only</p>
    </div>
    {#if state.counts[state.activeGroup] > 0}
      <label for={searchId}>Search {capabilityGroupLabels[state.activeGroup].toLowerCase()}</label>
      <input id={searchId} type="search" value={state.search} oninput={(event) => state.setSearch(event.currentTarget.value)} placeholder="Search by name or description" />
    {/if}
    {#if state.visibleCapabilities.length === 0}
      <p class="empty" role="status">{state.search.trim() ? 'No matching capabilities' : `No ${capabilityGroupLabels[state.activeGroup].toLowerCase()} available`}</p>
    {:else}
      <CapabilityCatalogGrid>
        {#each state.visibleCapabilities as capability (capability.kind + ':' + capability.key)}
          <li>
            {#if capability.kind === 'tool'}
              <CatalogueToolCard {capability} />
            {:else}
              <article class="capability">
                <div class="capability-heading">
                  <h5>{capability.name}</h5>
                  <span>{capability.kind === 'resource_template' ? 'Resource template' : capability.kind === 'resource' ? 'Resource' : 'Prompt'}</span>
                </div>
                <ToolDescription description={capability.description} />
              </article>
            {/if}
          </li>
        {/each}
      </CapabilityCatalogGrid>
    {/if}
  </div>
</section>

<style>
  .capabilities { border-top: 1px solid var(--admin-border); margin-top: 1.5rem; min-width: 0; padding-top: 1.25rem; }
  h3 { color: var(--admin-ink); font-size: 1rem; margin: 0 0 0.875rem; }
  nav { border-bottom: 1px solid var(--admin-border); display: flex; flex-wrap: wrap; gap: 0.25rem; }
  .capability-tab { align-items: center; background: transparent; border: 1px solid transparent; border-bottom-width: 3px; border-radius: 7px 7px 0 0; color: var(--admin-muted); cursor: pointer; display: flex; font: inherit; font-size: 0.875rem; font-weight: 650; gap: 0.45rem; margin-bottom: -1px; min-height: 2.75rem; padding: 0.65rem 0.8rem; }
  .capability-tab:hover { background: var(--admin-sidebar); color: var(--admin-ink); }
  .capability-tab.active { background: var(--admin-accent-soft); border-color: var(--admin-accent-border); border-bottom-color: var(--admin-accent); color: var(--admin-ink); font-weight: 750; }
  strong { background: var(--admin-sidebar); border: 1px solid var(--admin-border); border-radius: 999px; color: inherit; font-size: 0.7rem; min-width: 1.45rem; padding: 0.08rem 0.35rem; text-align: center; }
  .active strong { background: var(--admin-panel); border-color: var(--admin-accent-border); color: var(--admin-accent); }
  .catalogue { margin-top: 1rem; min-width: 0; }
  .catalogue-heading { align-items: baseline; display: flex; flex-wrap: wrap; gap: 0.5rem 1rem; justify-content: space-between; margin-bottom: 1rem; }
  h4 { font-size: 1rem; margin: 0; }
  .catalogue-heading p, .empty { color: var(--admin-muted); font-size: 0.8rem; margin: 0; }
  label { display: block; font-size: 0.8rem; font-weight: 600; margin-bottom: 0.4rem; }
  input { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); box-sizing: border-box; color: var(--admin-ink); font: inherit; font-size: 0.85rem; margin-bottom: 1rem; min-height: 2.75rem; padding: 0.65rem 0.8rem; width: 100%; }
  li { min-width: 0; }
  .capability { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); min-width: 0; overflow-wrap: anywhere; padding: 1rem; }
  .capability-heading { align-items: baseline; display: flex; flex-wrap: wrap; gap: 0.5rem; justify-content: space-between; }
  h5 { font-size: 0.9rem; margin: 0; }
  .capability-heading span { color: var(--admin-muted); font-size: 0.7rem; }
  button:focus-visible, input:focus-visible { outline: 3px solid var(--admin-focus); outline-offset: -3px; }
</style>
