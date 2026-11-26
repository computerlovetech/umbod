<script lang="ts">
  import { onMount } from 'svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import PlusIcon from '#lib/components/shared/PlusIcon.svelte';
  import Select from '#lib/components/admin/shared/Select.svelte';
  import DateTimeView from '#lib/components/shared/DateTimeView.svelte';
  import PersonalTokenDialog from './PersonalTokenDialog.svelte';
  import type { PersonalAccessTokensApi } from '#lib/personal-access-tokens/api.js';
  import { browserPersonalAccessTokensApi } from '#lib/personal-access-tokens/infrastructure/api.js';
  import { navigateToSignIn } from '#lib/admin/infrastructure/transport.js';
  import { BrowserNavigatorClipboardWriter, type ClipboardWriter } from '#lib/admin/clipboard.js';
  import { PersonalTokenState } from './personal-token-state.svelte';

  let { apiFactory = browserPersonalAccessTokensApi, clipboardFactory = (): ClipboardWriter => new BrowserNavigatorClipboardWriter(), signIn = navigateToSignIn }: {
    apiFactory?: () => PersonalAccessTokensApi;
    clipboardFactory?: () => ClipboardWriter;
    signIn?: () => void;
  } = $props();

  function createState(): PersonalTokenState {
    return new PersonalTokenState(apiFactory(), clipboardFactory());
  }

  const state = createState();
  onMount(() => { void state.load(); return state.dispose; });
</script>

<section id="telemetry-tokens" aria-labelledby="tokens-title">
  <header class="section-heading">
    <h2 id="tokens-title">Access tokens</h2>
    <p>Create and manage personal access tokens.</p>
  </header>
  <div class="admin-panel personal-tokens">
    <header class="card-heading">
      <h3>Personal access tokens</h3>
      {#if state.canGenerate}<Button disabled={state.pending} onclick={state.openCreate}><PlusIcon />Create access token</Button>{/if}
    </header>
    <div class="card-body">
      {#if state.status === 'loading'}
        <p role="status">Loading personal access tokens…</p>
      {:else if state.status === 'signin'}
        <p>Sign in to manage personal access tokens.</p>
        <Button onclick={signIn}>Sign in</Button>
      {:else if state.status === 'forbidden'}
        <p>Your account cannot manage personal access tokens on this instance.</p>
      {:else}
        {#if state.error && !state.createDialogOpen}<p class="admin-message admin-message--error" role="alert">{state.error}</p>{/if}
        {#if state.scopeOptions.length}
          <Select label="Permission" options={state.scopeOptions} value={state.selectedScope} onchange={state.selectScope} compact />
        {/if}
        <ul aria-label="Personal access tokens">
          {#each state.visibleTokens as token (token.token_id)}
            <li>
              <div>
                <strong>{token.name}</strong>
                <div class="hint">Permissions: {state.permissionsFor(token)}</div>
                <div class="hint">Expires <DateTimeView value={token.expires_at} /></div>
              </div>
              <span class={['status', token.status === 'active' && 'active']}>{token.status}</span>
              <Button variant="danger" size="compact" iconOnly disabled={state.pending || state.status !== 'ready'} onclick={(): Promise<void> => state.revoke(token.token_id)} aria-label={`Delete ${token.name}`} title={`Delete ${token.name}`}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18M9 6V4h6v2M5 6l1 14h12l1-14M10 10v6M14 10v6" /></svg>
              </Button>
            </li>
          {:else}
            <li>No personal access tokens.</li>
          {/each}
        </ul>
        {#if state.createDialogOpen}<PersonalTokenDialog {state} />{/if}
      {/if}
    </div>
    <footer>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6Zm-3 10 2 2 4-5" /></svg>
      Deleting a token immediately stops clients from using it.
    </footer>
  </div>
</section>

<style>
  h2, h3, p { margin: 0; }
  h2 { font-size: clamp(1.5rem, 3cqi, 1.85rem); letter-spacing: -.04em; line-height: 1.2; margin-bottom: .375rem; }
  h3 { font-size: 1rem; }
  .section-heading { margin-bottom: 1.25rem; }
  .personal-tokens { --card-padding: clamp(.875rem, 3cqi, 1.25rem); margin: 0; padding: 0; }
  .card-heading { align-items: center; display: flex; flex-wrap: wrap; justify-content: space-between; gap: 1rem; padding: 1rem var(--card-padding); }
  .card-body { padding: 0 var(--card-padding); }
  .card-body > p { margin-bottom: .75rem; font-size: .875rem; }
  p, .hint, footer { color: var(--admin-muted); }
  .hint, footer { font-size: .875rem; }
  ul { list-style: none; margin: .75rem 0 0; padding: 0; }
  li { align-items: center; border-top: 1px solid var(--admin-border); display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: .75rem; padding-block: 1rem; overflow-wrap: anywhere; }
  .status { background: var(--admin-soft); color: var(--admin-muted); border-radius: 999px; padding: .1875rem .5625rem; font-size: .75rem; font-weight: 650; }
  .status.active { background: var(--admin-accent-soft); color: var(--admin-accent); }
  footer { display: flex; align-items: center; gap: .5rem; padding: .875rem var(--card-padding); border-top: 1px solid var(--admin-border); background: var(--admin-soft); border-radius: 0 0 var(--admin-radius-panel) var(--admin-radius-panel); }
  footer svg { color: var(--admin-accent); flex: none; }
  @container (max-width: 24rem) {
    li { gap: .375rem; }
    .status { grid-column: 1; justify-self: start; }
    li :global(button) { grid-column: 2; grid-row: 1 / 3; }
  }
</style>
