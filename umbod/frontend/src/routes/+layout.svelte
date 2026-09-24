<script lang="ts">
  import { page } from '$app/state';
  import { ToastProvider } from '$lib/components/feedback';
  import AppHeader from '$lib/components/header/AppHeader.svelte';
  import '../app.css';
  import '$lib/styles/admin.css';

  let { children, data } = $props();

  const isAdminRoute = $derived(page.url.pathname.startsWith('/admin'));
</script>

<ToastProvider>
  {#if !isAdminRoute}
    <AppHeader accountIdentity={data.accountIdentity} />
  {/if}

  <main>
    {@render children()}
  </main>
</ToastProvider>
