<script lang="ts">
  import SetupProgress from '#lib/components/admin/shared/SetupProgress.svelte';
  import type { ConnectorListItem } from '#lib/admin/connectors.js';
  import ModalShell from '#lib/components/shared/ModalShell.svelte';
  import ConnectorConfigurationForm from './ConnectorConfigurationForm.svelte';
  import ConnectorIcon from './ConnectorIcon.svelte';
  import type { ConnectorCatalogState } from './connector-catalog-state.svelte';

  type ConnectorListForm = {
    status?: string;
    connectorId?: string;
    errorMessage?: string;
    successMessage?: string;
    values?: Record<string, string>;
    fieldMessages?: Record<string, string>;
  };

  let { state, connectors, form, onselect }: { state: ConnectorCatalogState; connectors: ConnectorListItem[]; form?: ConnectorListForm; onselect: (connectorId: string) => Promise<void> } = $props();
  const steps = ['Choose connector', 'Configure', 'Check & save'];
  const selectedConnector = $derived(state.selectedConnector(connectors));
</script>

<svelte:window onkeydown={state.handleKeydown} />

{#if state.open}
  <ModalShell title={state.mode === 'add' ? 'Add connector' : 'Configure connector'} titleId="connector-catalog-modal-title" close={state.close}
    initialFocus={state.mode === 'add' ? '[data-dialog-title]' : undefined}
    --modal-title-focus-outline={state.mode === 'add' ? 'none' : undefined}
    --modal-overflow={state.mode === 'add' ? 'auto' : undefined}
    --modal-width={state.mode === 'add' ? '39rem' : undefined}
    --modal-background={state.mode === 'add' ? 'linear-gradient(135deg, var(--admin-accent-soft), var(--admin-panel) 17rem)' : undefined}
    --admin-radius-panel={state.mode === 'add' ? '24px' : undefined}>
    {#snippet children()}
      {#snippet progress(current: number)}
        <SetupProgress {steps} {current} />
      {/snippet}
      {#if state.mode === 'add' && !selectedConnector?.configurationFields}
        <SetupProgress {steps} current={selectedConnector ? 2 : 1} />
      {/if}
      {#if selectedConnector}
        {#if selectedConnector.configurationFields}
          <ConnectorConfigurationForm
            connector={selectedConnector}
            fields={selectedConnector.configurationFields}
            operation="saveConfiguration"
            submitConnectorId={true}
            {form}
            onsaved={state.close}
            progress={state.mode === 'add' ? progress : undefined}
            onback={state.clearSelection}
          />
        {:else}
          <p class="empty" role="alert">This connector configuration could not be loaded.</p>
          {#if state.mode === 'add'}<button type="button" class="retry-back" onclick={state.clearSelection}>Back</button>{/if}
        {/if}
      {:else if connectors.some((connector) => !connector.isConfigured)}
        <h3>Choose a connector</h3>
        <ul aria-label="Available connectors">
          {#each connectors.filter((connector) => !connector.isConfigured) as connector (connector.id)}
            <li>
              <button type="button" onclick={() => onselect(connector.id)}>
                <ConnectorIcon label={connector.name} dataUrl={connector.iconDataUrl} />
                <span class="connector-copy">
                  <strong>{connector.name}</strong>
                  <span>{connector.description}</span>
                </span>
                <span class="arrow" aria-hidden="true">→</span>
              </button>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="empty">No connectors are available to add.</p>
      {/if}
    {/snippet}
  </ModalShell>
{/if}

<style>
  .empty { color: var(--admin-muted); margin: 1rem 0 0; }
  h3 { margin: 0; font-size: 1.0625rem; letter-spacing: -.02em; }
  .retry-back { margin-block-start: 1rem; }
  .arrow { margin-inline-start: auto; color: var(--admin-accent); }
  ul { display: grid; gap: 0.5rem; list-style: none; margin: 1rem 0 0; overflow: auto; padding: 0; }
  li button { align-items: flex-start; background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: 16px; cursor: pointer; display: flex; gap: 0.75rem; padding: 0.85rem; text-align: left; width: 100%; }
  li button:hover, li button:focus-visible { background: var(--admin-accent-soft); border-color: var(--admin-accent); }
  .connector-copy strong { color: var(--admin-ink); }
  .connector-copy { display: grid; gap: 0.3rem; }
  li span { color: var(--admin-muted); font-size: 13px; }
</style>
