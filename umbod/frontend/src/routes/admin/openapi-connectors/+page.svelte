<script lang="ts">
  import { invalidateAll } from '$app/navigation';
  import { page } from '$app/state';
  import { parseConnectorCapability } from '$lib/admin/connector-capabilities';
  import type { OpenApiConnectorCreateAction, OpenApiConnectorListPageData } from '$lib/admin/openapi-connectors';
  import AdminShell from '$lib/components/admin/AdminShell.svelte';
  import ConnectorPageHeader from '$lib/components/admin/connectors/ConnectorPageHeader.svelte';
  import ConnectorTabs from '$lib/components/admin/connectors/ConnectorTabs.svelte';
  import OpenApiConnectorList from '$lib/components/admin/openapi-connectors/OpenApiConnectorList.svelte';
  import OpenApiConnectorSetupModal from '$lib/components/admin/openapi-connectors/OpenApiConnectorSetupModal.svelte';
  import { OpenApiConnectorSetupState } from '$lib/components/admin/openapi-connectors/openapi-connector-setup-state.svelte';
  import { useToast } from '$lib/components/feedback';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';

  type PageData = OpenApiConnectorListPageData & { accountIdentity?: HeaderAccountIdentityState };
  type ActionData =
    | OpenApiConnectorCreateAction
    | {
        status?: string;
        mode?: 'file' | 'url';
        message?: string;
        retryable?: boolean;
        url?: string;
        approvedHosts?: string[];
        operationId?: string;
        activation_status?: string;
        connectorId?: string;
      }
    | null
    | undefined;

  let { data, form }: { data: PageData; form?: ActionData } = $props();
  const fallbackAccountIdentity: HeaderAccountIdentityState = { kind: 'hidden' };
  const listForm = $derived(form && !('displayName' in form) ? form : null);
  const setupState = new OpenApiConnectorSetupState(globalThis.fetch, useToast());

  async function retry(): Promise<void> {
    await invalidateAll();
  }
</script>

<svelte:head><title>OpenAPI connectors</title></svelte:head>

<AdminShell activeItem="connectors" accountIdentity={data.accountIdentity ?? fallbackAccountIdentity} contentWidth="wide">
  <div class="admin-page">
    <ConnectorPageHeader
      title="OpenAPI connectors"
      lede="Review registered OpenAPI connectors, import catalogs, and manage operation activation."
      addLabel="Add OpenAPI connector"
      onadd={(trigger) => setupState.showCreate(trigger)}
    />
    <ConnectorTabs activeTab="openapi" capability={parseConnectorCapability(page.url.searchParams.get('capability'))} />
    {#key data}
      <OpenApiConnectorList {data} form={listForm} onretry={retry} onconfigure={(event, connector) => { if (event.currentTarget instanceof HTMLElement) void setupState.showConfigure(event.currentTarget, connector.id, connector.name, connector.toolNamePrefix, connector.capabilityDescription); }} />
    {/key}
    <OpenApiConnectorSetupModal state={setupState} />
  </div>
</AdminShell>
