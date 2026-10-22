<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { CatalogueConnector } from '$lib/dashboard/domain/schemas';

  let { connector, children }: { connector: CatalogueConnector; children?: Snippet } = $props();
  const headingId = $props.id();
  const kindLabels = { native: 'Native', openapi: 'OpenAPI', downstream_mcp: 'MCP server' };
  const capabilityLabels = { tool: 'Tool', prompt: 'Prompt', resource: 'Resource', resource_template: 'Resource template' };
</script>

<article aria-labelledby={headingId}>
  <header>
    <h3 id={headingId}>{connector.display_name}</h3>
    <div class="badges">
      <span>{kindLabels[connector.kind]}</span>
      {#if connector.kind === 'downstream_mcp'}
        <span>{connector.ownership === 'personal' ? 'Personal' : 'Shared'}</span>
      {/if}
    </div>
  </header>
  {#if connector.capability_description}<p class="description">{connector.capability_description}</p>{/if}
  <details>
    <summary><span class="closed">Show details</span><span class="opened">Hide details</span><span class="sr-only"> for {connector.display_name}</span></summary>
    {#if children}
      <div class="personal-access">
        {@render children()}
      </div>
    {/if}
    <section aria-label="Capabilities" class="capabilities">
      <h4>Capabilities</h4>
      {#if connector.capabilities.length === 0}
        <p>No tools available</p>
      {:else}
        <ul>
          {#each connector.capabilities as capability (capability.kind + ':' + capability.key)}
            <li>
              {#if capability.description}
                <details class="capability">
                  <summary><span class="capability-name"><strong>{capability.name}</strong><span>{capabilityLabels[capability.kind]}</span></span></summary>
                  <p>{capability.description}</p>
                </details>
              {:else}
                <div class="capability-name"><strong>{capability.name}</strong><span>{capabilityLabels[capability.kind]}</span></div>
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  </details>
</article>

<style>
  article { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: 1.25rem; min-width: 0; overflow-wrap: anywhere; }
  header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.75rem; }
  h3 { margin: 0; font-size: 1.05rem; font-weight: 600; }
  h4 { margin: 0 0 0.75rem; font-size: 0.9rem; }
  .badges { display: flex; flex-wrap: wrap; gap: 0.4rem; }
  .badges span { background: var(--admin-accent-soft); color: var(--admin-muted); border-radius: var(--admin-radius); font-size: 0.75rem; padding: 0.25rem 0.5rem; }
  p { margin: 0.6rem 0; line-height: 1.55; }
  .description, li p { color: var(--admin-muted); font-size: 0.9rem; white-space: pre-line; }
  summary { color: var(--admin-accent); cursor: pointer; width: fit-content; padding: 0.6rem 0; font-size: 0.85rem; }
  summary:focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; border-radius: 2px; }
  .opened, details[open] > summary .closed { display: none; }
  details[open] > summary .opened { display: inline; }
  .capabilities, .personal-access { border-top: 1px solid var(--admin-border); padding-top: 1rem; margin-top: 0.5rem; }
  ul { list-style: none; padding: 0; margin: 0; }
  li + li { border-top: 1px solid var(--admin-border); margin-top: 0.75rem; padding-top: 0.75rem; }
  .capability-name { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 0.5rem; font-size: 0.9rem; }
  .capability-name span { color: var(--admin-muted); font-size: 0.75rem; }
  .capability > summary { width: auto; color: var(--admin-ink); }
  .capability > summary .capability-name { display: inline-flex; width: calc(100% - 1.25rem); vertical-align: middle; }
  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
</style>
