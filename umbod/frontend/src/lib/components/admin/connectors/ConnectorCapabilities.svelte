<script lang="ts">
  import { pushState } from '$app/navigation';
  import { untrack, type Snippet } from 'svelte';
  import { connectorCapabilities, connectorCapabilityUrl, parseConnectorCapability, type ConnectorCapability } from '$lib/admin/connector-capabilities';

  let { selected, counts, currentUrl, children }: {
    selected: ConnectorCapability;
    counts: Record<ConnectorCapability, number>;
    currentUrl: URL;
    children: Snippet<[ConnectorCapability]>;
  } = $props();
  let activeCapability = $state(untrack(() => selected));

  const labels: Record<ConnectorCapability, string> = {
    tools: 'Tools',
    prompts: 'Prompts',
    resources: 'Resources'
  };

  function navigate(event: MouseEvent, capability: ConnectorCapability): void {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    activeCapability = capability;
    pushState(connectorCapabilityUrl(currentUrl, capability), {});
  }

  function handlePopstate(): void {
    activeCapability = parseConnectorCapability(new URL(window.location.href).searchParams.get('capability'));
  }
</script>

<svelte:window onpopstate={handlePopstate} />

<section class="capabilities" aria-labelledby="connector-capabilities-heading">
  <h3 id="connector-capabilities-heading">Capabilities</h3>
  <nav aria-label="Connector capabilities">
    {#each connectorCapabilities as capability (capability)}
      <a
        class:active={activeCapability === capability}
        href={connectorCapabilityUrl(currentUrl, capability).toString()}
        aria-current={activeCapability === capability ? 'page' : undefined}
        onclick={(event) => navigate(event, capability)}
      >
        <span>{labels[capability]}</span>
        <strong>{counts[capability]}</strong>
      </a>
    {/each}
  </nav>
  <div class="catalog">
    {@render children(activeCapability)}
  </div>
</section>

<style>
  .capabilities { border-top: 1px solid var(--admin-border); margin-top: 1.5rem; min-width: 0; padding-top: 1.25rem; }
  h3 { color: var(--admin-ink); font-size: 1rem; margin: 0 0 0.875rem; }
  nav { border-bottom: 1px solid var(--admin-border); display: flex; flex-wrap: wrap; gap: 0.25rem; }
  a { align-items: center; border: 1px solid transparent; border-bottom-width: 3px; border-radius: 7px 7px 0 0; color: var(--admin-muted); display: flex; flex: 0 0 auto; font-size: 0.875rem; font-weight: 650; gap: 0.45rem; margin-bottom: -1px; padding: 0.65rem 0.8rem; text-decoration: none; }
  a:hover { background: var(--admin-sidebar); color: var(--admin-ink); }
  a:focus-visible { outline: 3px solid rgb(47 111 235 / 24%); outline-offset: -3px; }
  a.active { background: rgb(47 111 235 / 10%); border-color: rgb(47 111 235 / 20%); border-bottom-color: var(--admin-accent); color: var(--admin-ink); font-weight: 750; }
  strong { background: var(--admin-sidebar); border: 1px solid var(--admin-border); border-radius: 999px; color: inherit; font-size: 0.7rem; min-width: 1.45rem; padding: 0.08rem 0.35rem; text-align: center; }
  a.active strong { background: #fff; border-color: rgb(47 111 235 / 30%); color: var(--admin-accent); }
  .catalog { margin-top: 1rem; min-width: 0; }
</style>
