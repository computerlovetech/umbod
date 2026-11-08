<script lang="ts">
  import { onMount } from 'svelte';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
  import type { WorkspaceApi } from '$lib/workspace/api';
  import { workspaceApi } from '$lib/workspace/infrastructure/workspace-api';
  import { workspaceNavigation, workspacePresentation } from '$lib/workspace/navigation';
  import { WorkspaceAccessState } from '$lib/workspace/workspace-access-state.svelte';
  import WorkspaceShell from '$lib/components/shared/workspace/WorkspaceShell.svelte';
  import SubpageContainer from '$lib/components/shared/workspace/SubpageContainer.svelte';
  import SubpageNavigation, { type SubpageLink } from '$lib/components/shared/workspace/SubpageNavigation.svelte';
  import McpSetupGuide from './McpSetupGuide.svelte';
  import TelemetrySetup from './TelemetrySetup.svelte';

  let {
    mcpEndpoint,
    activePage = 'connect',
    accountIdentity = { kind: 'hidden' },
    createWorkspaceApi = workspaceApi
  }: {
    mcpEndpoint: string;
    activePage?: 'connect' | 'telemetry';
    accountIdentity?: HeaderAccountIdentityState;
    createWorkspaceApi?: () => WorkspaceApi;
  } = $props();

  function createAccess(): WorkspaceAccessState {
    return new WorkspaceAccessState(createWorkspaceApi());
  }

  const access = createAccess();
  const subpages: readonly SubpageLink[] = [
    { id: 'connect', label: 'Connect your harness', href: '/getting-started' },
    { id: 'telemetry', label: 'Set up telemetry', href: '/getting-started/telemetry' }
  ];

  onMount(() => {
    void access.load();
    return access.dispose;
  });
</script>

<svelte:head><title>Getting started · Umbod</title></svelte:head>

<WorkspaceShell {...workspacePresentation} navigationItems={workspaceNavigation(access.adminAccess === 'allowed')} activeItem="gettingStarted" accountIdentity={access.accountIdentity.kind === 'visible' ? access.accountIdentity : accountIdentity} contentWidth="wide">
  <SubpageContainer title="Getting started" lede="Connect your harness to Umbod, then optionally send telemetry with a personal access token.">
    {#snippet navigation()}
      <SubpageNavigation links={subpages} activeId={activePage} label="Setup sections" />
    {/snippet}
    {#if activePage === 'connect'}
      <McpSetupGuide {mcpEndpoint} />
    {:else}
      <TelemetrySetup />
    {/if}
  </SubpageContainer>
</WorkspaceShell>

