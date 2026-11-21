<script lang="ts">
  import { operationState } from '#lib/admin/operations/operation-state.svelte.js';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { onMount } from 'svelte';
  import ConnectorCatalogModal from '#lib/components/admin/connectors/ConnectorCatalogModal.svelte';
  import { getAddConnector } from '#lib/components/admin/connectors/add-connector-state.svelte.js';
  import ConnectorList from '#lib/components/admin/connectors/ConnectorList.svelte';
  import { ConnectorCatalogState } from '#lib/components/admin/connectors/connector-catalog-state.svelte.js';
  import { emptyPromptCatalog, emptyResourceCatalog } from '#lib/admin/capability-catalogs.js';
  import type { PageData } from './$types';

  type PublicationForm = {
    status?: string;
    successMessage?: string;
    errorMessage?: string;
  };

  let { data }: { data: PageData; form?: PublicationForm } = $props();
  const form = $derived(operationState.forOwner({ route: page.url.pathname, connectorId: (page.shallow?.url ?? page.url).searchParams.get('connector') ?? data.selectedConnectorId ?? data.connectors[0]?.id }) as PublicationForm);

  const catalogState = new ConnectorCatalogState();
  const addConnector = getAddConnector();

  onMount(() => addConnector.registerSetup({
    kind: 'native',
    nativeAvailable: () => data.nativeAvailable,
    nativeUnavailable: () => data.unavailableKinds.includes('native'),
    disabled: () => false,
    create: catalogState.show
  }));

  async function selectCatalogConnector(connectorId: string): Promise<void> {
    await goto(`?connector=${encodeURIComponent(connectorId)}`, { reset: false });
    catalogState.select(connectorId);
  }

  async function configureConnector(connectorId: string): Promise<void> {
    await goto(`?connector=${encodeURIComponent(connectorId)}`, { reset: false });
    catalogState.showConfigure(connectorId);
  }
</script>

{#key data}
    <ConnectorList
      unifiedRows={data.unifiedRows}
      unavailableKinds={data.unavailableKinds}
      connectors={data.connectors.filter((connector) => connector.isConfigured)}
      selectedConnectorId={data.selectedConnectorId}
      initialDetail={data.selectedDetail && data.selectedConnectorId ? { detail: data.selectedDetail, configurationFields: data.connectors.find((connector) => connector.id === data.selectedConnectorId)?.configurationFields ?? [], promptCatalog: data.selectedPromptCatalog ?? emptyPromptCatalog(), resourceCatalog: data.selectedResourceCatalog ?? emptyResourceCatalog(), invocationPolicies: data.invocationPolicies ?? [] } : undefined}
      initialDetailFailed={data.selectedDetailFailed}
      {form}
      onconfigure={configureConnector}
    />
{/key}
{#if data.status !== 'failed'}
  <ConnectorCatalogModal
    state={catalogState}
    connectors={data.connectors}
    {form}
    onselect={selectCatalogConnector}
    onbacktotype={() => addConnector.reopen('native')}
  />
{/if}
