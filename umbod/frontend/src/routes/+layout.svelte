<script lang="ts">
  import { page } from '$app/state';
  import { afterNavigate } from '$app/navigation';
  import { operationState } from '$lib/admin/operations/operation-state.svelte';
  import { ToastProvider } from '$lib/components/feedback';
  import AppHeader from '$lib/components/header/AppHeader.svelte';
  import '../app.css';
  import '$lib/styles/admin.css';

  let { children, data } = $props();

  const isAdminRoute = $derived(page.url.pathname.startsWith('/admin'));
  afterNavigate(() => operationState.resetForPath(`${page.url.pathname}${page.url.search}`));
</script>

<ToastProvider>
  {#if !isAdminRoute}
    <AppHeader accountIdentity={data.accountIdentity} />
  {/if}

  <main>
    {@render children()}
  </main>
</ToastProvider>
