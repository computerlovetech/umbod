<script lang="ts">
  import { navigating } from '$app/state';
  import type { ConnectorCapability } from '$lib/admin/connector-capabilities';
  import DelayedSpinner from '$lib/components/admin/shared/DelayedSpinner.svelte';

  type ConnectorTab = 'catalog' | 'openapi' | 'downstream-mcp';

  let { activeTab, capability = 'tools' }: { activeTab: ConnectorTab; capability?: ConnectorCapability } = $props();

  const tabs: Array<{ id: ConnectorTab; label: string; href: string }> = [
    { id: 'catalog', label: 'Connector catalog', href: '/admin/connectors' },
    { id: 'openapi', label: 'OpenAPI connectors', href: '/admin/openapi-connectors' },
    {
      id: 'downstream-mcp',
      label: 'MCP proxy connectors',
      href: '/admin/downstream-mcp-connectors'
    }
  ];
  const pendingTab = $derived(
    navigating.to !== null && navigating.to.url.pathname !== navigating.from?.url.pathname
      ? tabs.find((tab) => tab.href === navigating.to?.url.pathname)
      : undefined
  );
  const displayedActiveTab = $derived(pendingTab?.id ?? activeTab);
  const connectorTabLoading = $derived(pendingTab !== undefined);
</script>

<nav class="connector-tabs" aria-label="Connector type">
  {#each tabs as tab (tab.id)}
    <a class:active={displayedActiveTab === tab.id} href={`${tab.href}?capability=${capability}`} aria-current={displayedActiveTab === tab.id ? 'page' : undefined}>
      {tab.label}
    </a>
  {/each}
</nav>

{#if connectorTabLoading}
  <div class="connector-tabs-loading">
    <DelayedSpinner active label="Loading connectors" />
  </div>
{/if}

<style>
  .connector-tabs {
    border-bottom: 1px solid var(--admin-border);
    display: flex;
    gap: 24px;
    margin-bottom: 32px;
  }

  a {
    border-bottom: 2px solid transparent;
    color: var(--admin-muted);
    font-size: 14px;
    font-weight: 600;
    margin-bottom: -1px;
    padding: 0 2px 10px;
    text-decoration: none;
  }

  a:hover {
    color: var(--admin-ink);
  }

  a.active {
    border-bottom-color: var(--admin-accent);
    color: var(--admin-ink);
  }

  .connector-tabs-loading {
    display: flex;
    justify-content: center;
    margin: -16px 0 16px;
    min-height: 18px;
  }
</style>
