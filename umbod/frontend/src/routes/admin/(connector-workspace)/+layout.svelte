<script lang="ts">
  import { page } from '$app/state';
  import AdminShell from '#lib/components/admin/AdminShell.svelte';
  import SubpageContainer from '#lib/components/shared/workspace/SubpageContainer.svelte';
  import AddConnector from '#lib/components/admin/connectors/AddConnector.svelte';
  import { AddConnectorState, provideAddConnector } from '#lib/components/admin/connectors/add-connector-state.svelte.js';
  import type { LayoutProps } from './$types';

  let { data, children }: LayoutProps = $props();
  const addConnector = provideAddConnector(new AddConnectorState());
</script>

<svelte:head><title>Connectors</title></svelte:head>

<AdminShell activeItem="connectors" accountIdentity={data.accountIdentity ?? { kind: 'hidden' }} contentWidth="wide">
  <SubpageContainer headingId="mcp-workspace-heading" title="Connectors">
    {#snippet actions()}
      <AddConnector state={addConnector} unifiedRows={page.data.unifiedRows} unavailableKinds={page.data.unavailableKinds} />
    {/snippet}
    {@render children()}
  </SubpageContainer>
</AdminShell>
