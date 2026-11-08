<script lang="ts">
  import { onMount } from 'svelte';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import DateTimeView from '$lib/components/shared/DateTimeView.svelte';
  import TelemetryTokenDialog from './TelemetryTokenDialog.svelte';
  import type { PersonalAccessTokensApi } from '$lib/personal-access-tokens/api';
  import { browserPersonalAccessTokensApi } from '$lib/personal-access-tokens/infrastructure/api';
  import { navigateToSignIn } from '$lib/admin/infrastructure/transport';
  import { BrowserNavigatorClipboardWriter, type ClipboardWriter } from '$lib/admin/clipboard';
  import type { TelemetrySetupApi } from '$lib/telemetry-setup/api';
  import { browserTelemetrySetupApi } from '$lib/telemetry-setup/infrastructure/api';
  import { TelemetrySetupState } from './telemetry-setup-state.svelte';

  let { apiFactory = browserPersonalAccessTokensApi, setupApiFactory = browserTelemetrySetupApi, clipboardFactory = (): ClipboardWriter => new BrowserNavigatorClipboardWriter(), signIn = navigateToSignIn }: {
    apiFactory?: () => PersonalAccessTokensApi;
    setupApiFactory?: () => TelemetrySetupApi;
    clipboardFactory?: () => ClipboardWriter;
    signIn?: () => void;
  } = $props();

  function createState(): TelemetrySetupState {
    return new TelemetrySetupState(apiFactory(), setupApiFactory().setup, clipboardFactory());
  }

  const state = createState();
  onMount(() => { void state.load(); return state.dispose; });
</script>

<section class="admin-panel telemetry-setup" aria-label="Telemetry setup">
  <header>
    <h2>Telemetry tokens</h2>
    {#if state.canGenerate}<Button disabled={state.pending} onclick={state.openCreate}>Create token</Button>{/if}
  </header>
  <p>Manage tokens for sending agent logs to Umbod. Deleting a token immediately stops its use.</p>
  {#if state.status === 'loading'}
    <p role="status">Loading telemetry setup and personal access tokens…</p>
  {:else if state.status === 'signin'}
    <p>Sign in to manage personal access tokens.</p>
    <Button onclick={signIn}>Sign in</Button>
  {:else if state.status === 'forbidden'}
    <p>Your account cannot manage personal access tokens on this instance.</p>
  {:else}
    {#if !state.canGenerate && state.status === 'ready'}
      <p role="status">{state.availabilityMessage}</p>
    {/if}
    {#if state.error && !state.createDialogOpen}<p class="admin-message admin-message--error" role="alert">{state.error}</p>{/if}
    <ul aria-label="Personal access tokens">
      {#each state.tokens as token (token.token_id)}
        <li>
          <div><strong>{token.name}</strong> — {token.status}</div>
          <div class="hint">Expires <DateTimeView value={token.expires_at} /></div>
          <Button variant="danger" size="compact" iconOnly disabled={state.pending || state.status !== 'ready'} onclick={(): Promise<void> => state.revoke(token.token_id)} aria-label={`Delete ${token.name}`} title={`Delete ${token.name}`}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18M9 6V4h6v2M5 6l1 14h12l1-14M10 10v6M14 10v6" /></svg>
          </Button>
        </li>
      {:else}
        <li>No personal access tokens.</li>
      {/each}
    </ul>
    {#if state.createDialogOpen}<TelemetryTokenDialog {state} />{/if}
  {/if}
</section>

<style>
  .telemetry-setup { padding: 1.5rem; }
  h2 { color: var(--admin-ink); font-size: 20px; letter-spacing: -0.025em; margin: 0; }
  header { align-items: center; display: flex; flex-wrap: wrap; justify-content: space-between; gap: 16px; }
  p { color: var(--admin-muted); font-size: 14px; line-height: 1.6; }
  .hint { font-size: .875rem; color: var(--admin-muted); }
  ul { list-style: none; padding: 0; }
  li { align-items: center; border-top: 1px solid var(--admin-border); display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto; justify-items: start; gap: 16px; padding-block: 1rem; overflow-wrap: anywhere; }
  @media (max-width: 640px) {
    li { grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }
    .hint { grid-column: 1; }
    li :global(button) { grid-column: 2; grid-row: 1 / 3; }
  }
</style>
