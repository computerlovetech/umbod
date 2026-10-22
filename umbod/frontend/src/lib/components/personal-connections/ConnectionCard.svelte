<script lang="ts">
  import { tick } from 'svelte';
  import type { ConnectionState } from '$lib/personal-connections/state/connection-state.svelte';

  let { state, embedded = false }: { state: ConnectionState; embedded?: boolean } = $props();
  const headingId = $props.id();

  async function act(action: () => Promise<void>): Promise<void> {
    await action();
    await tick();
    if (document.activeElement === document.body) document.getElementById(headingId)?.focus();
  }
</script>

<svelte:element this={embedded ? 'section' : 'article'} class={embedded ? 'personal-access' : 'card'} aria-label={embedded ? 'Personal access' : state.selection.display_name} aria-busy={state.busy}>
  {#if embedded}
    <h4 id={headingId} tabindex="-1">Personal access</h4>
  {:else}
    <h2 id={headingId} tabindex="-1">{state.selection.display_name}</h2>
    <p>{state.selection.capability_description}</p>
  {/if}
  <dl>
    <div><dt>Personal access</dt><dd>{state.selection.enabled ? 'Enabled' : 'Disabled'}</dd></div>
    <div><dt>Authorization</dt><dd>{state.selection.has_authorization ? 'Authorization saved' : 'No authorization saved'}</dd></div>
    <div><dt>Authorization status</dt><dd aria-live="polite">
      {#if state.healthPhase === 'loading'}
        Checking authorization status…
      {:else if state.healthPhase === 'unavailable'}
        Authorization status unavailable
      {:else if state.health?.state === 'not_authorized'}
        Sign-in needed
      {:else if state.health?.state === 'authorized'}
        Authorization valid locally
      {:else if state.health?.state === 'expired'}
        Authorization expired
      {:else if state.health?.state === 'unsupported'}
        Sign in again to replace unsupported authorization
      {:else if state.health?.state === 'reconnect_required'}
        Sign in again required
      {:else if state.health?.state === 'refreshing'}
        Renewal in progress. Check status before another action.
      {/if}
    </dd></div>
    <div><dt>Tools</dt><dd>{state.selection.runtime_available ? 'Tools available' : 'Not available'}</dd></div>
  </dl>
  {#if state.healthPhase === 'ready' && state.health}
    {#if state.health.state === 'authorized' || state.health.state === 'expired'}
      <p>Expires: <time datetime={state.health.expires_at}>{new Date(state.health.expires_at).toLocaleString()}</time></p>
      <p class="hint">Last checked: {state.healthCheckedAt}</p>
    {:else if state.health.state === 'reconnect_required'}
      <p>{state.health.reason === 'provider_rejected' ? 'The provider rejected this authorization.' : state.health.reason === 'refresh_denied' ? 'Authorization renewal was rejected.' : 'The renewal outcome could not be confirmed.'}</p>
    {/if}
  {/if}
  <div class="actions">
    <button disabled={state.selection.enabled ? state.cleanupBlocked : state.busy || state.needsRefresh} onclick={state.setEnabled}>{state.selection.enabled ? 'Disable' : 'Enable'}</button>
    {#if state.selection.enabled}
      <button disabled={state.busy || state.needsRefresh || state.attempt !== null || state.renewalInProgress} onclick={() => act(state.start)}>{state.selection.has_authorization || (state.healthPhase === 'ready' && state.health && ['unsupported', 'expired', 'reconnect_required'].includes(state.health.state)) ? 'Sign in again' : 'Sign in'}</button>
    {/if}
    {#if state.selection.enabled && state.selection.has_authorization}
      <button disabled={!state.canDiscover} onclick={state.discover}>Discover tools</button>
    {/if}
    {#if state.canRenew}
      <button disabled={!state.canRenew} onclick={state.renew}>Renew authorization</button>
    {/if}
    {#if state.selection.has_authorization || state.attempt}
      <button disabled={state.cleanupBlocked} onclick={state.requestDisconnect}>Disconnect</button>
    {/if}
    <button disabled={state.busy} onclick={state.refresh}>Check authorization status</button>
  </div>
  {#if state.attempt}
    <section class="attempt" aria-label="Current sign-in">
      <h3>Sign-in {state.attempt.status}</h3>
      <p>Expires: <time datetime={state.attempt.expires_at}>{new Date(state.attempt.expires_at).toLocaleString()}</time></p>
      {#if state.authorizationUrl}
        <a href={state.authorizationUrl} target="_blank" rel="noopener noreferrer">Continue sign-in <span class="hint">(opens a new tab)</span></a>
      {/if}
      <div class="actions">
        <button disabled={state.busy || state.checking} onclick={() => act(state.check)}>Check sign-in status</button>
        <button disabled={state.busy || state.needsRefresh} onclick={() => act(state.cancel)}>Cancel sign-in</button>
      </div>
    </section>
  {/if}
  {#if state.confirmingDisconnect}
    <section class="confirmation" aria-label="Confirm disconnect">
      <p>Remove saved authorization and disable personal access? Any pending sign-in cannot restore it.</p>
      <div class="actions">
        <button disabled={state.cleanupBlocked} onclick={() => act(state.disconnect)}>Confirm disconnect</button>
        <button onclick={state.keepAuthorization}>Keep authorization</button>
      </div>
    </section>
  {/if}
  <div role="status" aria-live="polite">{state.message}</div>
  <div role="alert">{state.error}</div>
</svelte:element>

<style>
  .card { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: clamp(1rem, 3vw, 1.5rem); min-width: 0; overflow-wrap: anywhere; }
  h2 { margin: 0; font-size: 1.2rem; }
  h3, h4 { font-size: 1rem; }
  p { line-height: 1.6; }
  dl { display: grid; gap: 0.6rem; }
  dl div { display: flex; flex-wrap: wrap; gap: 0.5rem 1rem; justify-content: space-between; }
  dt { color: var(--admin-muted); }
  dd { margin: 0; font-weight: 600; }
  .hint { color: var(--admin-muted); font-size: 0.9rem; }
  .actions { display: flex; flex-wrap: wrap; gap: 0.65rem; margin: 1rem 0; }
  button { background: var(--admin-panel); color: var(--admin-ink); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: 0.65rem 0.85rem; font: inherit; cursor: pointer; min-height: 2.75rem; }
  button:hover:not(:disabled) { border-color: var(--admin-accent); }
  button:disabled { opacity: 0.55; cursor: not-allowed; }
  a { color: var(--admin-accent); }
  a:focus-visible, button:focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
  .attempt, .confirmation { border-top: 1px solid var(--admin-border); margin-top: 1rem; padding-top: 0.5rem; }
  [role='status'], [role='alert'] { line-height: 1.6; }
  [role='alert'] { color: var(--admin-danger, var(--admin-ink)); }
</style>
