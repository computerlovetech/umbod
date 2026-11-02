<script lang="ts">
  import { page } from '$app/state';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import { navigateToSignIn } from '$lib/admin/infrastructure/transport';
  import { logoutNavigation, type LogoutNavigation } from '$lib/admin/infrastructure/logout';

  let { logout = logoutNavigation }: { logout?: LogoutNavigation } = $props();
  let loggingOut = $state(false);

  async function handleLogout(): Promise<void> {
    if (loggingOut) return;
    loggingOut = true;
    await logout.logout();
  }

  const accessDenied = $derived(page.status === 401 || page.status === 403);
  const message = $derived(page.status === 401
    ? 'Your sign-in was not accepted by the API. Sign in again or contact your administrator.'
    : page.status === 403
      ? 'You do not have permission to access this administration area. Contact your administrator.'
      : 'This page could not be loaded. Please try again later.');
</script>

<svelte:head>
  <title>{accessDenied ? 'Access denied' : 'Page unavailable'}</title>
</svelte:head>

<section class="error-page admin-page" aria-labelledby="error-heading">
  <h1 id="error-heading" class="admin-title">{accessDenied ? 'Access denied' : 'Page unavailable'}</h1>
  <p class="admin-lede">{message}</p>
  <div class="error-actions">
    {#if page.status === 401}
      <Button onclick={navigateToSignIn}>Sign in again</Button>
    {/if}
    {#if accessDenied}
      <Button variant="secondary" disabled={loggingOut} onclick={handleLogout}>Log out</Button>
    {/if}
  </div>
</section>

<style>
  .error-page { max-width: 42rem; margin: 0 auto; padding: 64px 24px; }
  .error-actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 24px; }
</style>
