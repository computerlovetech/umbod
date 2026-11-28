<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import type { PortableConnectors } from '#lib/admin/portable-connectors/port.js';
  import { connectorWorkspaceHref, portableConfigurationStatus, portableDuplicateReference, type PortableConnectorRow } from '#lib/admin/unified-connectors.js';
  import { useToast } from '#lib/components/feedback/index.js';
  import type { AddConnectorState } from '../connectors/add-connector-state.svelte.js';
  import ConnectorKindBadge from '../connectors/ConnectorKindBadge.svelte';
  import UnifiedConnectorWorkspace from '../connectors/UnifiedConnectorWorkspace.svelte';
  import PortableConnectorConfiguration from './PortableConnectorConfiguration.svelte';
  import { PortableConnectorWorkspaceState, type PortableConnectorWorkspaceData } from './portable-connector-workspace-state.svelte.js';

  let { data, api, addConnector, navigate }: {
    data: PortableConnectorWorkspaceData;
    api: PortableConnectors;
    addConnector: AddConnectorState;
    navigate: (href: string) => Promise<void>;
  } = $props();

  const state = untrack(() => new PortableConnectorWorkspaceState(data, api));
  const toast = useToast();

  onMount(() => addConnector.registerSetup({
    kind: 'portable',
    nativeAvailable: () => state.data.nativeAvailable,
    nativeUnavailable: () => state.data.unavailableKinds.includes('native'),
    disabled: () => false
  }));

  async function select(row: PortableConnectorRow): Promise<void> {
    if (row.id === state.configuration?.connector.id) return;
    try {
      await navigate(connectorWorkspaceHref(row, null));
    } catch {
      toast.error('Could not open this portable connector. Try again.');
    }
  }
</script>

<UnifiedConnectorWorkspace
  kind="portable"
  items={state.items}
  unifiedRows={state.data.unifiedRows}
  unavailableKinds={state.data.unavailableKinds}
  selectedId={state.configuration?.connector.id}
  detailLabel="Portable connector configuration"
  onselect={select}
>
  {#snippet metadata(row)}
    {@const reference = portableDuplicateReference(row, state.items)}
    <ConnectorKindBadge label="Portable" />
    <span class="connector-meta">{row.status} · {portableConfigurationStatus(row.configured)}{reference ? ` · ${reference}` : ''}</span>
  {/snippet}
  {#snippet actions()}{/snippet}
  {#snippet detail()}
    {#if state.configuration}
      <PortableConnectorConfiguration state={state.configuration} />
    {:else}
      <p class="empty">No submitted portable connector selected.</p>
    {/if}
  {/snippet}
</UnifiedConnectorWorkspace>

<style>
  .empty { color: var(--admin-muted); }
</style>
