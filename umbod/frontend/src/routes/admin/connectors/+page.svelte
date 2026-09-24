<script lang="ts">
  import { goto, invalidateAll } from '$app/navigation';
  import { page } from '$app/state';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import AdminShell from '$lib/components/admin/AdminShell.svelte';
  import ConnectorCatalogModal from '$lib/components/admin/connectors/ConnectorCatalogModal.svelte';
  import ConnectorList from '$lib/components/admin/connectors/ConnectorList.svelte';
  import ConnectorPageHeader from '$lib/components/admin/connectors/ConnectorPageHeader.svelte';
  import { ConnectorCatalogState } from '$lib/components/admin/connectors/connector-catalog-state.svelte';
  import ConnectorTabs from '$lib/components/admin/connectors/ConnectorTabs.svelte';
  import { emptyPromptCatalog, emptyResourceCatalog, type PromptCatalog, type ResourceCatalog } from '$lib/admin/capability-catalogs';
  import type { InvocationPolicyTool } from '$lib/admin/invocation-policy';
  import { parseConnectorCapability } from '$lib/admin/connector-capabilities';
  import type { ConnectorListPageData } from '$lib/admin/connectors';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';

  type ConnectorListAdminPageData = ConnectorListPageData & {
    accountIdentity?: HeaderAccountIdentityState;
    selectedConnectorId?: string;
    selectedDetail?: Extract<import('$lib/admin/connectors').ConnectorDetailPageData, { status: 'ready' }>;
    selectedPromptCatalog?: PromptCatalog;
    selectedResourceCatalog?: ResourceCatalog;
    invocationPolicies?: InvocationPolicyTool[];
    selectedDetailFailed?: true;
  };

  type PublicationForm = {
    status?: string;
    successMessage?: string;
    errorMessage?: string;
  };

  let { data, form }: { data: ConnectorListAdminPageData; form?: PublicationForm } = $props();

  const fallbackAccountIdentity: HeaderAccountIdentityState = { kind: 'hidden' };
  const catalogState = new ConnectorCatalogState();

  async function retry(): Promise<void> {
    await invalidateAll();
  }

  async function selectCatalogConnector(connectorId: string): Promise<void> {
    await goto(`?connector=${encodeURIComponent(connectorId)}`, { keepFocus: true, noScroll: true });
    catalogState.select(connectorId);
  }

  async function configureConnector(connectorId: string): Promise<void> {
    await goto(`?connector=${encodeURIComponent(connectorId)}`, { keepFocus: true, noScroll: true });
    catalogState.showConfigure(connectorId);
  }
</script>

<svelte:head>
  <title>Connectors</title>
</svelte:head>

<AdminShell activeItem="connectors" accountIdentity={data.accountIdentity ?? fallbackAccountIdentity} contentWidth="wide">
  <div class="admin-page">
    <ConnectorPageHeader
      title="Connectors"
      lede="Review available and registered connectors."
      addLabel="Add connector"
      onadd={() => catalogState.show()}
    />

    <ConnectorTabs activeTab="catalog" capability={parseConnectorCapability(page.url.searchParams.get('capability'))} />

    {#if data.status === 'ready'}
      {#key data}
        <ConnectorList
          connectors={data.connectors.filter((connector) => connector.isConfigured)}
          selectedConnectorId={data.selectedConnectorId}
          initialDetail={data.selectedDetail && data.selectedConnectorId ? { detail: data.selectedDetail, configurationFields: data.connectors.find((connector) => connector.id === data.selectedConnectorId)?.configurationFields ?? [], promptCatalog: data.selectedPromptCatalog ?? emptyPromptCatalog(), resourceCatalog: data.selectedResourceCatalog ?? emptyResourceCatalog(), invocationPolicies: data.invocationPolicies ?? [] } : undefined}
          initialDetailFailed={data.selectedDetailFailed}
          {form}
          onconfigure={configureConnector}
        />
      {/key}
    {:else if data.status === 'empty'}
      <p class="admin-message">{data.message}</p>
    {:else}
      <div class="admin-message admin-message-error failure-state">
        <p>{data.message}</p>
        <Button onclick={retry}>{data.retryLabel}</Button>
      </div>
    {/if}
    {#if data.status !== 'failed'}
      <ConnectorCatalogModal
        state={catalogState}
        connectors={data.connectors}
        {form}
        onselect={selectCatalogConnector}
      />
    {/if}
  </div>
</AdminShell>

<style>
  .failure-state p {
    margin: 0 0 12px;
  }
</style>
