<script lang="ts">
  import { navigating } from '$app/state';
  import type { ConnectorCapability } from '$lib/admin/connector-capabilities';
  import SubpageNavigation from '$lib/components/shared/workspace/SubpageNavigation.svelte';
  import { ConnectorTabsState, type ConnectorTab } from './connector-tabs-state.svelte';

  let { activeTab, capability = 'tools' }: { activeTab: ConnectorTab; capability?: ConnectorCapability } = $props();
  const state = new ConnectorTabsState(() => activeTab, () => capability, () => navigating);
</script>

<SubpageNavigation links={state.links} activeId={state.activeId} label="Connector type" pending={state.pending} loadingLabel="Loading connectors" />
