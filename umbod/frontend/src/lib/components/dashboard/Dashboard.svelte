<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import { browserTransport, navigateToSignIn } from '#lib/admin/infrastructure/transport.js';
  import PersonalActivity from '#lib/components/personal/activity/PersonalActivity.svelte';
  import { DashboardActivityState } from '#lib/dashboard/state/dashboard-activity-state.svelte.js';
  import type { ActivityApi } from '#lib/insights/activity/domain/activity-api.js';
  import { createActivityApi } from '#lib/insights/activity/infrastructure/activity-api.js';
  import { useWorkspace } from '#lib/workspace/workspace-context.js';

  let {
    createApi = (): ActivityApi => createActivityApi(browserTransport()),
    signIn = navigateToSignIn
  }: {
    createApi?: () => ActivityApi;
    signIn?: () => void;
  } = $props();

  const workspace = useWorkspace();

  function createState(): DashboardActivityState {
    return new DashboardActivityState(createApi(), workspace);
  }

  const dashboard = createState();
  onDestroy(workspace.registerDisposal(dashboard.dispose));
  $effect.pre(dashboard.observeAccount);

  onMount((): (() => void) => {
    dashboard.start(document.visibilityState === 'visible');
    return dashboard.dispose;
  });

  function observeFocus(): void {
    if (document.visibilityState === 'visible' && !dashboard.checking && !workspace.personalChecking) void dashboard.revalidate();
  }

  function handleSignIn(): void {
    dashboard.dispose();
    signIn();
  }
</script>

<svelte:head><title>Dashboard · Umbod</title></svelte:head>
<svelte:window onfocus={observeFocus} />
<svelte:document onvisibilitychange={() => dashboard.observeVisibility(document.visibilityState === 'visible')} />

<div class="dashboard">
  <h1 class="admin-title">Dashboard</h1>
  {#if dashboard.activity?.access === 'sign-in' || workspace.access.adminAccess === 'sign-in'}
    <p class="admin-message" role="status">Sign in to view your activity.</p>
    <Button onclick={handleSignIn}>Sign in</Button>
  {:else if dashboard.activity?.access === 'forbidden'}
    <p class="admin-message" role="alert">Access to activity is unavailable.</p>
    <Button onclick={dashboard.revalidate}>Try again</Button>
  {:else if dashboard.activity}
    <PersonalActivity state={dashboard.activity} />
  {:else if dashboard.checking || workspace.personalChecking}
    <p class="admin-message" role="status">Loading activity…</p>
  {:else if workspace.personalUnavailable}
    <p class="admin-message" role="alert">Could not load your account.</p>
    <Button onclick={dashboard.revalidate}>Try again</Button>
  {:else}
    <p class="admin-message" role="status">A verified account is required to view your activity.</p>
  {/if}
</div>

<style>
  .dashboard { min-width: 0; }
</style>
