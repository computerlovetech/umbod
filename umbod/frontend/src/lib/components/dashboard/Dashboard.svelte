<script lang="ts">
  import { onMount } from 'svelte';
  import { workspaceNavigation, workspacePresentation } from '$lib/workspace/navigation';
  import type { CurrentUserApi } from '$lib/workspace/admin-access';
  import { WorkspaceAccessState } from '$lib/workspace/workspace-access-state.svelte';
  import { adminApi } from '$lib/admin/infrastructure/admin-api';
  import { navigateToSignIn } from '$lib/admin/infrastructure/transport';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
  import type { DashboardApi } from '$lib/dashboard/api';
  import { browserDashboardApi } from '$lib/dashboard/infrastructure/dashboard-api';
  import { DashboardState } from '$lib/dashboard/state/dashboard-state.svelte';
  import type { PersonalConnectionsApi } from '$lib/personal-connections/api';
  import { browserPersonalConnectionsApi } from '$lib/personal-connections/infrastructure/personal-connections-api';
  import WorkspaceShell from '$lib/components/shared/workspace/WorkspaceShell.svelte';
  import McpSetupGuide from '$lib/components/shared/mcp-setup/McpSetupGuide.svelte';
  import ConnectorCard from './ConnectorCard.svelte';
  import ConnectionCard from '$lib/components/personal-connections/ConnectionCard.svelte';

  let {
    mcpEndpoint,
    createCurrentUserApi = adminApi,
    accountIdentity = { kind: 'hidden' },
    createApi = browserDashboardApi,
    createPersonalApi = browserPersonalConnectionsApi,
    signIn = navigateToSignIn
  }: {
    mcpEndpoint: string;
    createCurrentUserApi?: () => CurrentUserApi;
    accountIdentity?: HeaderAccountIdentityState;
    createApi?: () => DashboardApi;
    createPersonalApi?: () => PersonalConnectionsApi;
    signIn?: () => void;
  } = $props();

  function createState(): DashboardState {
    return new DashboardState(createApi(), createPersonalApi());
  }

  function createAccessState(): WorkspaceAccessState {
    return new WorkspaceAccessState(createCurrentUserApi());
  }

  const state = createState();
  const workspaceAccess = createAccessState();

  onMount(() => {
    void state.loadCatalogue();
    void workspaceAccess.load();
    return () => {
      state.dispose();
      workspaceAccess.dispose();
    };
  });
</script>

<svelte:head><title>Dashboard · Umbod</title></svelte:head>
<svelte:window onfocus={state.refreshOnFocus} />
<svelte:document onvisibilitychange={() => { if (document.visibilityState === 'visible') void state.refreshOnFocus(); }} />

<WorkspaceShell {...workspacePresentation} navigationItems={workspaceNavigation(workspaceAccess.adminAccess === 'allowed')} activeItem="dashboard" accountIdentity={workspaceAccess.accountIdentity.kind === 'visible' ? workspaceAccess.accountIdentity : accountIdentity} contentWidth="wide">
  <div class="dashboard">
    <h1 class="admin-title">Dashboard</h1>
    <section class="catalogue" aria-labelledby="connectors-heading" aria-busy={state.phase === 'loading' || state.refreshing}>
      <div class="section-heading">
        <h2 id="connectors-heading">Connectors</h2>
        {#if state.phase === 'ready'}<button aria-label="Refresh connectors" disabled={state.refreshing} onclick={state.loadCatalogue}>Refresh</button>{/if}
      </div>
      {#if state.catalogueError}
        <div class="feedback" role="alert">
          <span>{state.catalogueError}</span>
          <button disabled={state.refreshing} onclick={state.loadCatalogue}>Retry</button>
        </div>
      {/if}
      {#if state.phase === 'loading'}
        <p role="status">Loading connectors…</p>
      {:else if state.phase === 'sign-in'}
        <p role="alert">Sign in required</p>
        <button onclick={() => { state.dispose(); signIn(); }}>Sign in</button>
      {:else if state.phase === 'forbidden'}
        <p role="alert">Access unavailable</p>
        <button onclick={state.loadCatalogue}>Retry</button>
      {:else if state.phase === 'error'}
        <p role="alert">Couldn't load connectors</p>
        <button onclick={state.loadCatalogue}>Retry</button>
      {:else if state.connectors.length === 0}
        <p role="status">No connectors available</p>
      {:else}
        {#if state.personalPhase === 'error' || state.personalPhase === 'unavailable'}
          <div class="feedback" role="status">
            <span>{state.personalPhase === 'error' ? "Couldn't load personal access" : 'Personal access unavailable'}</span>
            <button onclick={state.loadPersonal}>Retry personal access</button>
          </div>
        {/if}
        <ul class="connectors">
          {#each state.connectors as connector (connector.kind + ':' + connector.connector_id)}
            <li>
              {#snippet personalActions()}
                {@const card = state.personalCard(connector.connector_id)}
                {#if card}
                  <ConnectionCard state={card} embedded />
                {:else}
                  <p role="status">{state.personalPhase === 'loading' ? 'Loading personal access…' : 'Personal access unavailable'}</p>
                {/if}
              {/snippet}
              <ConnectorCard {connector} children={connector.ownership === 'personal' ? personalActions : undefined} />
            </li>
          {/each}
        </ul>
      {/if}
    </section>
    <section class="setup" aria-label="MCP client setup">
      <McpSetupGuide {mcpEndpoint} compact />
    </section>
  </div>
</WorkspaceShell>

<style>
  .dashboard { max-width: 960px; }
  .catalogue { margin-top: 2rem; }
  h2 { font-size: 1rem; margin: 0; }
  .section-heading { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; }
  .connectors { display: grid; gap: 1rem; list-style: none; padding: 0; margin: 0; }
  li { min-width: 0; }
  .setup { margin-top: 2rem; }
  .feedback { display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem; margin-bottom: 1rem; }
  p { color: var(--admin-muted); line-height: 1.6; }
  button { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); color: var(--admin-ink); font: inherit; cursor: pointer; padding: 0.6rem 0.9rem; min-height: 2.75rem; }
  button:focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
  [role='alert'] { color: var(--admin-danger); }
</style>
