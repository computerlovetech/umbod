<script lang="ts">
  import { useWorkspace } from '$lib/workspace/workspace-context';
  import { WorkspaceIdentityBinding } from '$lib/workspace/workspace-scope.svelte';
  import { onMount, onDestroy } from 'svelte';
  import DelayedSpinner from '$lib/components/admin/shared/DelayedSpinner.svelte';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import { navigateToSignIn } from '$lib/admin/infrastructure/transport';
  import type { DashboardApi } from '$lib/dashboard/api';
  import { browserDashboardApi } from '$lib/dashboard/infrastructure/dashboard-api';
  import { DashboardState } from '$lib/dashboard/state/dashboard-state.svelte';
  import type { PersonalConnectionsApi } from '$lib/personal-connections/api';
  import type { AuthorizationBrowser } from '$lib/personal-connections/authorization-browser';
  import { browserAuthorizationBrowser } from '$lib/personal-connections/infrastructure/browser-authorization-browser';
  import { browserPersonalConnectionsApi } from '$lib/personal-connections/infrastructure/personal-connections-api';
  import PageContainer from '$lib/components/shared/workspace/PageContainer.svelte';
  import ConnectorWorkspace from './ConnectorWorkspace.svelte';

  let {
    createApi = browserDashboardApi,
    createPersonalApi = browserPersonalConnectionsApi,
    createAuthorizationBrowser = browserAuthorizationBrowser,
    signIn = navigateToSignIn
  }: {
    createApi?: () => Pick<DashboardApi, 'catalogue'>;
    createPersonalApi?: () => PersonalConnectionsApi;
    createAuthorizationBrowser?: () => AuthorizationBrowser;
    signIn?: () => void;
  } = $props();

  function createState(): DashboardState {
    return new DashboardState(createApi(), createPersonalApi(), createAuthorizationBrowser());
  }

  const state = createState();
  const workspace = useWorkspace();
  const identity = new WorkspaceIdentityBinding(workspace.access, state.observeAccountIdentity);
  onDestroy(workspace.registerDisposal(state.dispose));

  $effect.pre(identity.observe);

  onMount(() => {
    void state.initialize(new URL(window.location.href).searchParams.get('connector') ?? '');
    return () => {
      state.dispose();
    };
  });
</script>

<svelte:head><title>Connectors · Umbod</title></svelte:head>
<svelte:window onfocus={state.refreshOnFocus} />
<svelte:document onvisibilitychange={() => { if (document.visibilityState === 'visible') void state.refreshOnFocus(); }} />

<PageContainer>
  {#snippet identity()}
    <h1 id="connectors-heading" class="admin-title">Connectors</h1>
  {/snippet}
  {#snippet children()}
  <section aria-labelledby="connectors-heading" aria-busy={state.phase === 'loading' || state.refreshing}>
    {#if state.catalogueError}
      <div class="feedback" role="alert">
        <span>{state.catalogueError}</span>
        <Button variant="secondary" disabled={state.refreshing} onclick={state.loadCatalogue}>Retry</Button>
      </div>
    {/if}
    {#if state.phase === 'loading'}
      <DelayedSpinner active label="Loading connectors" />
    {:else if state.phase === 'sign-in'}
      <p role="alert">Sign in required</p>
      <Button onclick={() => { state.dispose(); signIn(); }}>Sign in</Button>
    {:else if state.phase === 'forbidden'}
      <p role="alert">Access unavailable</p>
      <Button variant="secondary" onclick={state.loadCatalogue}>Retry</Button>
    {:else if state.phase === 'error'}
      <p role="alert">Couldn't load connectors</p>
      <Button variant="secondary" onclick={state.loadCatalogue}>Retry</Button>
    {:else if state.connectors.length === 0}
      <p role="status">No connectors available</p>
    {:else}
      {#if state.personalPhase === 'error' || state.personalPhase === 'unavailable'}
        <div class="feedback" role="status">
          <span>{state.personalPhase === 'error' ? "Couldn't load personal access" : 'Personal access unavailable'}</span>
          <Button variant="secondary" onclick={state.loadPersonal}>Retry personal access</Button>
        </div>
      {/if}
      <ConnectorWorkspace {state} />
    {/if}
  </section>
  {/snippet}
</PageContainer>

<style>
  .feedback { display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem; margin-bottom: 1rem; }
  p { color: var(--admin-muted); line-height: 1.6; }
  [role='alert'] { color: var(--admin-danger); }
</style>
