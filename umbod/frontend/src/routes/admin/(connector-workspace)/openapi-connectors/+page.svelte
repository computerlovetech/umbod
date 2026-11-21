<script lang="ts">
  import { operationState } from '#lib/admin/operations/operation-state.svelte.js';
  import { page } from '$app/state';
  import { onMount } from 'svelte';
  import type { OpenApiConnectorCreateAction } from '#lib/admin/openapi-connectors.js';
  import { getAddConnector } from '#lib/components/admin/connectors/add-connector-state.svelte.js';
  import OpenApiConnectorList from '#lib/components/admin/openapi-connectors/OpenApiConnectorList.svelte';
  import OpenApiConnectorSetupModal from '#lib/components/admin/openapi-connectors/OpenApiConnectorSetupModal.svelte';
  import { OpenApiConnectorSetupState } from '#lib/components/admin/openapi-connectors/openapi-connector-setup-state.svelte.js';
  import { useToast } from '#lib/components/feedback/index.js';
  import type { PageData } from './$types';
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
  const form = $derived(operationState.forOwner({ route: page.url.pathname, connectorId: (page.shallow?.url ?? page.url).searchParams.get('connector') ?? data.connectors[0]?.id }) as ActionData);
  const listForm = $derived(form && !('displayName' in form) ? form : null);
  const addConnector = getAddConnector();
  const setupState = new OpenApiConnectorSetupState(globalThis.fetch, useToast());

  onMount(() => addConnector.registerSetup({
    kind: 'openapi',
    nativeAvailable: () => data.nativeAvailable,
    nativeUnavailable: () => data.unavailableKinds.includes('native'),
    disabled: () => false,
    create: setupState.showCreate
  }));

</script>

{#key data}
  <OpenApiConnectorList {data} unifiedRows={data.unifiedRows} unavailableKinds={data.unavailableKinds} form={listForm} onconfigure={(event, connector) => { if (event.currentTarget instanceof HTMLElement) void setupState.showConfigure(event.currentTarget, connector.id, connector.name, connector.toolNamePrefix, connector.capabilityDescription); }} />
{/key}
<OpenApiConnectorSetupModal state={setupState} onbacktotype={() => addConnector.reopen('openapi')} />
