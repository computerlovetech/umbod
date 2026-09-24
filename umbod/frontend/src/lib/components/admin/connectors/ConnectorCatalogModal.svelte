<script lang="ts">
  import type { ConnectorListItem } from '$lib/admin/connectors';
  import AdminModalShell from '$lib/components/admin/shared/AdminModalShell.svelte';
  import ConnectorConfigurationForm from './ConnectorConfigurationForm.svelte';
  import ConnectorIcon from './ConnectorIcon.svelte';
  import type { ConnectorCatalogState } from './connector-catalog-state.svelte';

  type ConnectorListForm = {
    status?: string;
    connectorId?: string;
    errorMessage?: string;
    successMessage?: string;
    values?: Record<string, string>;
  };

  let { state, connectors, form, onselect }: { state: ConnectorCatalogState; connectors: ConnectorListItem[]; form?: ConnectorListForm; onselect: (connectorId: string) => Promise<void> } = $props();
  const selectedConnector = $derived(state.selectedConnector(connectors));
</script>

<svelte:window onkeydown={state.handleKeydown} />

{#if state.open}
  <AdminModalShell title={state.mode === 'add' ? 'Add connector' : 'Configure connector'} titleId="connector-catalog-modal-title" close={state.close}>
    {#snippet children()}
      {#if selectedConnector}
        {#if state.mode === 'add'}
          <button class="back" type="button" onclick={state.clearSelection}>← Available connectors</button>
        {/if}
        {#if selectedConnector.configurationFields}
          <ConnectorConfigurationForm
            connector={selectedConnector}
            fields={selectedConnector.configurationFields}
            action="?/saveConfiguration"
            submitConnectorId={true}
            {form}
            onsaved={state.close}
          />
        {:else}
          <p class="empty">This connector configuration could not be loaded.</p>
        {/if}
      {:else if connectors.some((connector) => !connector.isConfigured)}
        <p class="intro">Select a connector to configure and add it.</p>
        <ul aria-label="Available connectors">
          {#each connectors.filter((connector) => !connector.isConfigured) as connector (connector.id)}
            <li>
              <button type="button" onclick={() => onselect(connector.id)}>
                <ConnectorIcon label={connector.name} dataUrl={connector.iconDataUrl} />
                <span class="connector-copy">
                  <strong>{connector.name}</strong>
                  <span>{connector.description}</span>
                </span>
              </button>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="empty">No connectors are available to add.</p>
      {/if}
    {/snippet}
  </AdminModalShell>
{/if}

<style>
  .intro, .empty { color: #787774; margin: 1rem 0 0; }
  .back { background: transparent; border: 0; color: #56554f; cursor: pointer; font: inherit; margin-top: 1rem; padding: 0; }
  ul { display: grid; gap: 0.5rem; list-style: none; margin: 1rem 0 0; overflow: auto; padding: 0; }
  li button { align-items: flex-start; background: #fbfbfa; border: 1px solid #e9e9e7; border-radius: 8px; cursor: pointer; display: flex; gap: 0.6rem; padding: 0.85rem; text-align: left; width: 100%; }
  li button:hover { background: #f4f4f2; }
  .connector-copy { display: grid; gap: 0.3rem; }
  li span { color: #787774; font-size: 13px; }
</style>
