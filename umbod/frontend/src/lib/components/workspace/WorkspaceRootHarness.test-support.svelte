<script lang="ts">
  import RootLayout from '../../../routes/+layout.svelte';
  import WorkspaceLayout from '../../../routes/(workspace)/+layout.svelte';
  import type { WorkspaceRoute } from './workspace-route.test-support.svelte';

  let { route }: { route: WorkspaceRoute } = $props();
  const data = { accountIdentity: { kind: 'hidden' as const } };
</script>

<RootLayout {data}>
  {#if route.inWorkspace}
    <WorkspaceLayout {data} params={{}}>
      {#key route.pathname}
        <h1>{route.pathname}</h1>
      {/key}
    </WorkspaceLayout>
  {:else}
    <h1>Outside workspace</h1>
  {/if}
</RootLayout>
