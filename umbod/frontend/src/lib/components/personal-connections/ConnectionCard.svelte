<script lang="ts">
  import { tick } from 'svelte';
  import type { PersonalConnectionController } from '$lib/personal-connections/state/port';
  import { PersonalAccessViewState } from '$lib/personal-connections/state/access-view-state.svelte';
  import ConnectionActions from './ConnectionActions.svelte';
  import ConnectionStatusBadge from './ConnectionStatusBadge.svelte';

  let { state, embedded = false }: { state: PersonalConnectionController; embedded?: boolean } = $props();
  const headingId = $props.id();
  const view = new PersonalAccessViewState(() => state);

  async function act(action: () => Promise<void>): Promise<void> {
    await action();
    await tick();
    if (document.activeElement === document.body) document.getElementById(headingId)?.focus();
  }
</script>

<svelte:element this={embedded ? 'section' : 'article'} class={embedded ? 'personal-access' : 'card'} aria-label={embedded ? 'Personal access' : state.selection.display_name} aria-busy={state.busy || state.checking}>
  <header>
    {#if embedded}
      <h4 id={headingId} tabindex="-1">Personal access</h4>
    {:else}
      <h2 id={headingId} tabindex="-1">{state.selection.display_name}</h2>
    {/if}
    <div class="header-status" aria-live="polite"><ConnectionStatusBadge status={view.status} /></div>
    {#if !embedded}<ConnectionActions {state} />{/if}
  </header>
  {#if !embedded}<p class="connector-description">{state.selection.capability_description}</p>{/if}
  <p class="status-description">{view.status.description}</p>
  <details class="connection-details">
    <summary>Connection details</summary>
    <dl>
      <div><dt>Personal access</dt><dd>{state.selection.enabled ? 'Enabled' : 'Disabled'}</dd></div>
      <div><dt>Authorization</dt><dd>{state.selection.has_authorization ? 'Authorization saved' : 'No authorization saved'}</dd></div>
      <div><dt>Authorization status</dt><dd>{view.healthLabel}</dd></div>
      <div><dt>Tools</dt><dd>{state.selection.runtime_available ? 'Tools available' : 'Not available'}</dd></div>
      {#if state.healthPhase === 'ready' && state.health && (state.health.state === 'authorized' || state.health.state === 'expired')}
        <div><dt>Expires</dt><dd><time datetime={state.health.expires_at}>{new Date(state.health.expires_at).toLocaleString()}</time></dd></div>
      {/if}
      {#if state.healthCheckedAt}<div><dt>Last checked</dt><dd>{state.healthCheckedAt}</dd></div>{/if}
      {#if state.attempt}
        <div><dt>Sign-in status</dt><dd>{state.attempt.status}</dd></div>
        <div><dt>Sign-in expires</dt><dd><time datetime={state.attempt.expires_at}>{new Date(state.attempt.expires_at).toLocaleString()}</time></dd></div>
      {/if}
    </dl>
    <p class="hint">Authorization checks use saved records, not a live provider connection test.</p>
  </details>
  {#if state.confirmingDisconnect}
    <section class="confirmation" aria-label="Confirm disconnect">
      <h5>Disconnect personal access?</h5>
      <p>Remove saved authorization and disable personal access? Any pending sign-in cannot restore it.</p>
      <div class="confirmation-actions">
        <button class="danger" type="button" disabled={state.cleanupBlocked} onclick={() => act(state.disconnect)}>Confirm disconnect</button>
        <button type="button" onclick={state.keepAuthorization}>Keep authorization</button>
      </div>
    </section>
  {/if}
  {#if state.message}<p class="feedback" role="status">{state.message}</p>{/if}
  {#if state.healthRefreshError}<p class="feedback" role="status">{state.healthRefreshError}</p>{/if}
  {#if state.error}<p class="error" role="alert">{state.error}</p>{/if}
</svelte:element>

<style>
  .card { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: clamp(1rem, 3vw, 1.5rem); min-width: 0; overflow-wrap: anywhere; }
  .personal-access { min-width: 0; overflow-wrap: anywhere; }
  header { align-items: center; display: flex; flex-wrap: wrap; gap: 0.65rem; padding-top: 1rem; }
  .card header { padding-top: 0; }
  h2, h4 { color: var(--admin-ink); font-size: 0.9rem; margin: 0; }
  h2 { font-size: 1.1rem; }
  .header-status { margin-left: auto; }
  p { line-height: 1.6; }
  .status-description, .connector-description { color: var(--admin-muted); font-size: 0.85rem; margin: 0.75rem 0 0; }
  button { align-items: center; box-sizing: border-box; background: var(--admin-panel); border: 1px solid var(--admin-border-strong); border-radius: 6px; color: var(--admin-ink); cursor: pointer; display: inline-flex; font: inherit; font-size: 0.85rem; font-weight: 600; gap: 0.5rem; justify-content: center; line-height: 1.4; min-height: 2.75rem; padding: 0.6rem 0.9rem; text-decoration: none; }
  button:hover:not(:disabled) { background: var(--admin-hover); }
  button:disabled { opacity: 0.55; cursor: not-allowed; }
  .connection-details { border-top: 1px solid var(--admin-border); font-size: 0.8rem; margin-top: 1rem; padding-top: 0.85rem; }
  summary { color: var(--admin-muted); cursor: pointer; font-weight: 600; width: fit-content; }
  summary:hover { color: var(--admin-accent); }
  dl { display: grid; gap: 0.6rem; margin: 1rem 0 0; }
  dl div { display: flex; flex-wrap: wrap; gap: 0.3rem 1rem; justify-content: space-between; }
  dt { color: var(--admin-muted); }
  dd { margin: 0; text-align: right; }
  .hint { color: var(--admin-muted); font-size: 0.75rem; margin: 0.85rem 0 0; }
  button:focus-visible, summary:focus-visible { outline: 3px solid var(--admin-focus); outline-offset: 3px; }
  .confirmation { background: var(--admin-danger-bg); border: 1px solid var(--admin-danger-border); border-radius: var(--admin-radius); color: var(--admin-danger-text); margin-top: 1rem; padding: 1rem; }
  h5 { font-size: 0.85rem; margin: 0; }
  .confirmation p { font-size: 0.8rem; margin: 0.5rem 0 0; }
  .confirmation-actions { display: flex; flex-wrap: wrap; gap: 0.6rem; margin-top: 0.85rem; }
  .danger { background: var(--admin-danger); border-color: var(--admin-danger); color: var(--admin-on-action); }
  .danger:hover:not(:disabled) { background: var(--admin-danger-hover); }
  .feedback, .error { font-size: 0.8rem; margin: 0.85rem 0 0; }
  .feedback { color: var(--admin-muted); }
  .error { color: var(--admin-danger); }
</style>
