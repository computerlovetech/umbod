<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import DelayedSpinner from '$lib/components/admin/shared/DelayedSpinner.svelte';
  import { logoutNavigation } from '$lib/admin/infrastructure/logout';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import { workspaceNavigation, workspacePresentation } from '$lib/workspace/navigation';
  import type { WorkspaceApi } from '$lib/workspace/api';
  import { WorkspaceAccessState } from '$lib/workspace/workspace-access-state.svelte';
  import { workspaceApi } from '$lib/workspace/infrastructure/workspace-api';
  import { navigateToSignIn } from '$lib/admin/infrastructure/transport';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
  import type { DashboardApi } from '$lib/dashboard/api';
  import { browserDashboardApi } from '$lib/dashboard/infrastructure/dashboard-api';
  import { DashboardState } from '$lib/dashboard/state/dashboard-state.svelte';
  import type { PersonalConnectionsApi } from '$lib/personal-connections/api';
  import type { AuthorizationBrowser } from '$lib/personal-connections/authorization-browser';
  import { browserAuthorizationBrowser } from '$lib/personal-connections/infrastructure/browser-authorization-browser';
  import { browserPersonalConnectionsApi } from '$lib/personal-connections/infrastructure/personal-connections-api';
  import WorkspaceShell from '$lib/components/shared/workspace/WorkspaceShell.svelte';
  import ConnectorWorkspace from './ConnectorWorkspace.svelte';

  let {
    createWorkspaceApi = workspaceApi,
    accountIdentity = { kind: 'hidden' },
    createApi = browserDashboardApi,
    createPersonalApi = browserPersonalConnectionsApi,
    createAuthorizationBrowser = browserAuthorizationBrowser,
    signIn = navigateToSignIn
  }: {
    createWorkspaceApi?: () => WorkspaceApi;
    accountIdentity?: HeaderAccountIdentityState;
    createApi?: () => Pick<DashboardApi, 'catalogue'>;
    createPersonalApi?: () => PersonalConnectionsApi;
    createAuthorizationBrowser?: () => AuthorizationBrowser;
    signIn?: () => void;
  } = $props();

  function createState(): DashboardState {
    return new DashboardState(createApi(), createPersonalApi(), createAuthorizationBrowser());
  }

  function createAccessState(): WorkspaceAccessState {
    return new WorkspaceAccessState(createWorkspaceApi(), () => accountIdentity);
  }

  const state = createState();
  const workspaceAccess = createAccessState();

  $effect.pre(() => {
    const sourceIdentity = accountIdentity;
    const sourceChanged = untrack(() => workspaceAccess.observeIdentitySource(sourceIdentity));
    const identity = workspaceAccess.effectiveAccountIdentity;
    untrack(() => state.observeAccountIdentity(identity, sourceChanged));
  });

  onMount(() => {
    void state.loadCatalogue();
    void workspaceAccess.load();
    return () => {
      state.dispose();
      workspaceAccess.dispose();
    };
  });
</script>

<svelte:head><title>Connectors · Umbod</title></svelte:head>
<svelte:window onfocus={state.refreshOnFocus} />
<svelte:document onvisibilitychange={() => { if (document.visibilityState === 'visible') void state.refreshOnFocus(); }} />

<WorkspaceShell {...workspacePresentation} navigationItems={workspaceNavigation(workspaceAccess.adminAccess === 'allowed')} activeItem="connectors" logout={{ logout: async (): Promise<void> => { state.dispose(); workspaceAccess.dispose(); await logoutNavigation.logout(); } }} accountIdentity={workspaceAccess.effectiveAccountIdentity} contentWidth="wide">
  <div class="dashboard">
    <h1 id="connectors-heading" class="admin-title">Connectors</h1>
    <p class="intro">Explore the connectors and capabilities available to your account.</p>
    <section class="catalogue" aria-labelledby="connectors-heading" aria-busy={state.phase === 'loading' || state.refreshing}>
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
        <ConnectorWorkspace {state} canManage={workspaceAccess.adminAccess === 'allowed'} />
      {/if}
    </section>
  </div>
</WorkspaceShell>

<style>
  .dashboard { min-width: 0; }
  .intro { font-size: 0.9rem; margin: 0.65rem 0 0; }
  .catalogue { margin-top: 1.75rem; }
  .feedback { display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem; margin-bottom: 1rem; }
  p { color: var(--admin-muted); line-height: 1.6; }
  [role='alert'] { color: var(--admin-danger); }
</style>
