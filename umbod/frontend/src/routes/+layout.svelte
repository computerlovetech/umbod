<script lang="ts">
  import { page } from '$app/state';
  import { afterNavigate, beforeNavigate } from '$app/navigation';
  import { WorkspaceNavigationHistory } from '#lib/workspace/navigation-history.svelte.js';
  import { provideWorkspaceNavigationHistory } from '#lib/workspace/navigation-history-context.js';
  import { operationState } from '#lib/admin/operations/operation-state.svelte.js';
  import { usesWorkspaceShell } from '#lib/workspace/navigation.js';
  import { ToastProvider } from '#lib/components/feedback/index.js';
  import IdentityObservation from '#lib/components/identity-directory/IdentityObservation.svelte';
  import AppHeader from '#lib/components/header/AppHeader.svelte';
  import '../app.css';
  import '#lib/styles/admin.css';

  let { children, data } = $props();

  function hasSuccessfulRoute(): boolean {
    return page.error === null && page.status < 400 && page.route.id !== null;
  }

  const navigationHistory = new WorkspaceNavigationHistory(new URL(page.url.href), hasSuccessfulRoute());
  provideWorkspaceNavigationHistory(navigationHistory);

  beforeNavigate(({ from, to, shallow }) => {
    if (!shallow) navigationHistory.startNavigation(from?.url ?? null, to?.url ?? null, hasSuccessfulRoute());
  });
  afterNavigate(({ shallow }) => {
    if (shallow) return;
    navigationHistory.completeNavigation(new URL(page.url.href), hasSuccessfulRoute());
    operationState.resetForPath(`${page.url.pathname}${page.url.search}`);
  });
</script>

<IdentityObservation />

<ToastProvider>
  {#if !usesWorkspaceShell(page.url.pathname)}
    <AppHeader accountIdentity={data.accountIdentity} />
  {/if}

  <main>
    {@render children()}
  </main>
</ToastProvider>
