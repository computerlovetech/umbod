<script lang="ts">
  import { operationState } from '$lib/admin/operations/operation-state.svelte';
  import { invalidateAll } from '$app/navigation';
  import { page } from '$app/state';
  import { parseConnectorCapability } from '$lib/admin/connector-capabilities';
  import type { OpenApiConnectorCreateAction, OpenApiConnectorListPageData } from '$lib/admin/openapi-connectors';
  import AdminShell from '$lib/components/admin/AdminShell.svelte';
  import SubpageContainer from '$lib/components/shared/workspace/SubpageContainer.svelte';
  import Button from '$lib/components/admin/shared/Button.svelte';
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

  let { data }: { data: PageData; form?: ActionData } = $props();
  const form = $derived(operationState.forOwner({ route: page.url.pathname, connectorId: page.url.searchParams.get('connector') ?? data.connectors[0]?.id }) as ActionData);
  const fallbackAccountIdentity: HeaderAccountIdentityState = { kind: 'hidden' };
  const listForm = $derived(form && !('displayName' in form) ? form : null);
  const setupState = new OpenApiConnectorSetupState(globalThis.fetch, useToast());

  async function retry(): Promise<void> {
    await invalidateAll();
  }
</script>

<svelte:head><title>OpenAPI connectors</title></svelte:head>

<AdminShell activeItem="connectors" accountIdentity={data.accountIdentity ?? fallbackAccountIdentity} contentWidth="wide">
  <SubpageContainer title="OpenAPI connectors" lede="Review registered OpenAPI connectors, import catalogs, and manage operation activation.">
    {#snippet actions()}
      <Button aria-label="Add OpenAPI connector" onclick={(event) => setupState.showCreate(event.currentTarget)}><span aria-hidden="true">+</span> Add OpenAPI connector</Button>
    {/snippet}
    {#snippet navigation()}
      <ConnectorTabs activeTab="openapi" capability={parseConnectorCapability(page.url.searchParams.get('capability'))} />
    {/snippet}
    {#key data}
      <OpenApiConnectorList {data} form={listForm} onretry={retry} onconfigure={(event, connector) => { if (event.currentTarget instanceof HTMLElement) void setupState.showConfigure(event.currentTarget, connector.id, connector.name, connector.toolNamePrefix, connector.capabilityDescription); }} />
    {/key}
    <OpenApiConnectorSetupModal state={setupState} />
  </SubpageContainer>
</AdminShell>
