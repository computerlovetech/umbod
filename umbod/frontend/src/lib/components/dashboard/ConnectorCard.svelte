<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { CatalogueConnector } from '$lib/dashboard/domain/schemas';
  import ConnectorIcon from '$lib/components/admin/connectors/ConnectorIcon.svelte';

  let { connector, children }: { connector: CatalogueConnector; children?: Snippet } = $props();
  const headingId = $props.id();
  const kindLabels = { native: 'Native', openapi: 'OpenAPI', downstream_mcp: 'MCP server' };
  const capabilityLabels = { tool: 'Tool', prompt: 'Prompt', resource: 'Resource', resource_template: 'Resource template' };
</script>

<article aria-labelledby={headingId}>
  <details class="connector-details">
    <summary class="connector-summary">
      <ConnectorIcon label={connector.display_name} size="medium" />
      <span class="connector-info">
        <span class="connector-name" id={headingId}>{connector.display_name}</span>
        {#if connector.capability_description}<span class="description">{connector.capability_description}</span>{/if}
        <span class="metadata">
          <span>{kindLabels[connector.kind]}</span>
          <span>{connector.ownership === 'personal' ? 'Personal' : 'Shared'}</span>
          <span>{connector.capabilities.length} {connector.capabilities.length === 1 ? 'capability' : 'capabilities'}</span>
        </span>
      </span>
      <span class="detail-toggle"><span class="closed">Show details</span><span class="opened">Hide details</span><span class="sr-only"> for {connector.display_name}</span><span class="chevron" aria-hidden="true">›</span></span>
    </summary>
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
  article { background: var(--admin-panel); min-width: 0; overflow-wrap: anywhere; }
  h4 { margin: 0 0 0.75rem; font-size: 0.9rem; }
  .connector-summary { display: flex; align-items: center; gap: 0.85rem; width: auto; padding: 1rem; color: var(--admin-ink); list-style: none; }
  .connector-summary::-webkit-details-marker { display: none; }
  .connector-summary:hover { background: var(--admin-accent-soft); }
  .connector-info { display: grid; gap: 0.3rem; min-width: 0; flex: 1; }
  .connector-name { font-size: 0.95rem; font-weight: 600; }
  .metadata { display: flex; flex-wrap: wrap; align-items: center; gap: 0.35rem 0.6rem; color: var(--admin-muted); font-size: 0.75rem; }
  .metadata > span + span::before { content: '·'; margin-right: 0.6rem; }
  .detail-toggle { display: flex; align-items: center; gap: 0.65rem; flex-shrink: 0; color: var(--admin-muted); font-size: 0.75rem; }
  .chevron { font-size: 1.4rem; transition: transform 120ms ease; }
  .connector-details[open] > summary .chevron { transform: rotate(90deg); }
  .connector-details > .capabilities, .connector-details > .personal-access { margin: 0 1rem 1rem; }
  @media (max-width: 600px) {
    .connector-summary { align-items: flex-start; gap: 0.65rem; }
    .detail-toggle > .closed, .detail-toggle > .opened { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
  }
  p { margin: 0.6rem 0; line-height: 1.55; }
  .description, li p { color: var(--admin-muted); font-size: 0.85rem; }
  .description { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  li p { white-space: pre-line; }
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
