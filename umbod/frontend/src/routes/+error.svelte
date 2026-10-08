<script lang="ts">
  import { page } from '$app/state';
  import { navigateToSignIn } from '$lib/admin/infrastructure/transport';

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
  {#if page.status === 401}
    <button type="button" onclick={navigateToSignIn}>Sign in again</button>
  {/if}
</section>

<style>
  .error-page { max-width: 42rem; margin: 0 auto; padding: 64px 24px; }
  button { margin-top: 24px; padding: 10px 16px; border: 1px solid var(--admin-action); border-radius: var(--admin-radius); background: var(--admin-action); color: var(--admin-on-action); font: inherit; cursor: pointer; }
  button:hover { background: var(--admin-action-hover); }
</style>
