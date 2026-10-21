<script lang="ts">
  import { onMount } from 'svelte';
  import { navigateToSignIn } from '$lib/admin/infrastructure/transport';
  import type { PersonalConnectionsApi } from '$lib/personal-connections/api';
  import { browserPersonalConnectionsApi } from '$lib/personal-connections/infrastructure/personal-connections-api';
  import { ConnectionsState } from '$lib/personal-connections/state/connections-state.svelte';
  import ConnectionCard from './ConnectionCard.svelte';

  let { createApi = browserPersonalConnectionsApi, signIn = navigateToSignIn }: {
    createApi?: () => PersonalConnectionsApi;
    signIn?: () => void;
  } = $props();
  function createState(): ConnectionsState {
    return new ConnectionsState(createApi());
  }

  const state = createState();

  onMount(() => {
    void state.load();
    return state.dispose;
  });
</script>

<svelte:head><title>Connections · Umbod</title></svelte:head>

<section class="page" aria-labelledby="connections-title">
  <h1 id="connections-title">Connections</h1>
  <p>Manage your personal MCP connections. Enabling, saving authorization and discovering tools are separate actions.</p>
  <p class="hint">Administrator approval, activation, permissions, your authorization and discovery are independent requirements. “Not available” does not identify which requirement is missing.</p>

  {#if state.phase === 'loading'}
    <p role="status">Loading connections…</p>
  {:else if state.phase === 'sign-in'}
    <section aria-label="Sign-in required">
      <p role="alert">Sign in to view your connections. Previous account details have been cleared.</p>
      <button onclick={() => { state.dispose(); signIn(); }}>Sign in to Umbod</button>
    </section>
  {:else if state.phase === 'unavailable'}
    <p role="status">Personal connections are not available for this instance or account.</p>
    <button onclick={state.load}>Refresh connections</button>
  {:else if state.phase === 'error'}
    <p role="alert">Connections could not be loaded. No changes were requested.</p>
    <button onclick={state.load}>Refresh connections</button>
  {:else if state.cards.length === 0}
    <p role="status">No eligible personal connections are listed for your account.</p>
    <button onclick={state.load}>Refresh connections</button>
  {:else}
    <div class="cards">
      {#each state.cards as card (card.selection.connector_id)}
        <ConnectionCard state={card} />
      {/each}
    </div>
  {/if}
</section>

<style>
  .page { max-width: 54rem; padding: clamp(1rem, 4vw, 2rem); margin: 0 auto; color: var(--admin-ink); }
  h1 { font-size: clamp(1.8rem, 4vw, 2.25rem); }
  p { line-height: 1.65; }
  .hint { color: var(--admin-muted); font-size: 0.95rem; }
  .cards { display: grid; gap: 1.25rem; margin-top: 1.5rem; }
  button { background: var(--admin-panel); color: var(--admin-ink); font: inherit; padding: 0.65rem 1rem; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); min-height: 2.75rem; cursor: pointer; }
  button:focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
</style>
