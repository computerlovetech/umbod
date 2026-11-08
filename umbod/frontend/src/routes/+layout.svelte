<script lang="ts">
  import { page } from '$app/state';
  import { afterNavigate } from '$app/navigation';
  import { operationState } from '$lib/admin/operations/operation-state.svelte';
  import { usesWorkspaceShell } from '$lib/workspace/navigation';
  import { ToastProvider } from '$lib/components/feedback';
  import IdentityObservation from '$lib/components/identity-directory/IdentityObservation.svelte';
  import AppHeader from '$lib/components/header/AppHeader.svelte';
  import '../app.css';
  import '$lib/styles/admin.css';

  let { children, data } = $props();

  afterNavigate(() => operationState.resetForPath(`${page.url.pathname}${page.url.search}`));
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
