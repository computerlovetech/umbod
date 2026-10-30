<script lang="ts">
  import { page } from '$app/state';
  import { afterNavigate } from '$app/navigation';
  import { operationState } from '$lib/admin/operations/operation-state.svelte';
  import { ToastProvider } from '$lib/components/feedback';
  import IdentityObservation from '$lib/components/identity-directory/IdentityObservation.svelte';
  import AppHeader from '$lib/components/header/AppHeader.svelte';
  import '../app.css';
  import '$lib/styles/admin.css';

  let { children, data } = $props();

  const hasWorkspaceShell = $derived(page.url.pathname.startsWith('/admin') || page.url.pathname === '/dashboard' || page.url.pathname === '/files');
  afterNavigate(() => operationState.resetForPath(`${page.url.pathname}${page.url.search}`));
</script>

<IdentityObservation />

<ToastProvider>
  {#if !hasWorkspaceShell}
    <AppHeader accountIdentity={data.accountIdentity} />
  {/if}

  <main>
    {@render children()}
  </main>
</ToastProvider>
