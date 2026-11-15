<script lang="ts">
  import { useWorkspace } from '$lib/workspace/workspace-context';
  import { WorkspaceIdentityBinding } from '$lib/workspace/workspace-scope.svelte';
  import { onMount, onDestroy } from 'svelte';
  import PersonalUsage from './PersonalUsage.svelte';
  import { navigateToSignIn } from '$lib/admin/infrastructure/transport';
  import type { DashboardApi } from '$lib/dashboard/api';
  import { browserDashboardApi } from '$lib/dashboard/infrastructure/dashboard-api';
  import { UsagePageState } from '$lib/dashboard/state/usage-page-state.svelte';

  let {
    createApi = browserDashboardApi,
    signIn = navigateToSignIn
  }: {
    createApi?: () => Pick<DashboardApi, 'usage'>;
    signIn?: () => void;
  } = $props();

  function createState(): UsagePageState {
    return new UsagePageState(createApi().usage);
  }

  const state = createState();
  const workspace = useWorkspace();
  const identity = new WorkspaceIdentityBinding(workspace.access, state.observeAccountIdentity);
  onDestroy(workspace.registerDisposal(state.dispose));

  $effect.pre(identity.observe);

  onMount(() => {
    void state.usage.refresh();
    return () => {
      state.dispose();
    };
  });
</script>

<svelte:head><title>Dashboard · Umbod</title></svelte:head>
<svelte:window onfocus={state.refreshOnFocus} />
<svelte:document onvisibilitychange={() => { if (document.visibilityState === 'visible') void state.refreshOnFocus(); }} />

<div class="dashboard">
  <h1 class="admin-title">Dashboard</h1>
  <PersonalUsage state={state.usage} signIn={() => { state.dispose(); signIn(); }} />
</div>

<style>
  .dashboard { min-width: 0; }
</style>
