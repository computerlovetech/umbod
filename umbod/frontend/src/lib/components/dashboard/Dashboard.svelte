<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import PersonalUsage from './PersonalUsage.svelte';
  import { logoutNavigation } from '$lib/admin/infrastructure/logout';
  import { workspaceNavigation, workspacePresentation } from '$lib/workspace/navigation';
  import type { WorkspaceApi } from '$lib/workspace/api';
  import { WorkspaceAccessState } from '$lib/workspace/workspace-access-state.svelte';
  import { workspaceApi } from '$lib/workspace/infrastructure/workspace-api';
  import { navigateToSignIn } from '$lib/admin/infrastructure/transport';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
  import type { DashboardApi } from '$lib/dashboard/api';
  import { browserDashboardApi } from '$lib/dashboard/infrastructure/dashboard-api';
  import { UsagePageState } from '$lib/dashboard/state/usage-page-state.svelte';
  import WorkspaceShell from '$lib/components/shared/workspace/WorkspaceShell.svelte';

  let {
    createWorkspaceApi = workspaceApi,
    accountIdentity = { kind: 'hidden' },
    createApi = browserDashboardApi,
    signIn = navigateToSignIn
  }: {
    createWorkspaceApi?: () => WorkspaceApi;
    accountIdentity?: HeaderAccountIdentityState;
    createApi?: () => Pick<DashboardApi, 'usage'>;
    signIn?: () => void;
  } = $props();

  function createState(): UsagePageState {
    return new UsagePageState(createApi().usage);
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
    void state.usage.refresh();
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

<WorkspaceShell {...workspacePresentation} navigationItems={workspaceNavigation(workspaceAccess.adminAccess === 'allowed')} activeItem="dashboard" logout={{ logout: async (): Promise<void> => { state.dispose(); workspaceAccess.dispose(); await logoutNavigation.logout(); } }} accountIdentity={workspaceAccess.effectiveAccountIdentity} contentWidth="wide">
  <div class="dashboard">
    <h1 class="admin-title">Dashboard</h1>
    <PersonalUsage state={state.usage} signIn={() => { state.dispose(); signIn(); }} />
  </div>
</WorkspaceShell>

<style>
  .dashboard { min-width: 0; }
</style>
