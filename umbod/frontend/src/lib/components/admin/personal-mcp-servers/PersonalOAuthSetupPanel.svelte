<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import Button from '../shared/Button.svelte';
  import LoadingButton from '../shared/LoadingButton.svelte';
  import AdminToggle from '../shared/AdminToggle.svelte';
  import DateTimeView from '$lib/components/shared/DateTimeView.svelte';
  import type { PersonalOAuthSetupState } from './personal-oauth-setup-state.svelte';

  let { state, connectorId }: { state: PersonalOAuthSetupState; connectorId: string } = $props();
  const lifetime = untrack(() => ({ state, connectorId }));
  onMount(() => { void lifetime.state.load(lifetime.connectorId); return lifetime.state.detach; });
</script>

<section class="setup admin-panel" aria-label="Personal OAuth setup">
  <h3>OAuth setup</h3>
  {#if state.accessDenied}
    <p role="alert">Administration access was lost. Sign in again before reloading this page.</p>
  {:else}
    <div class="validation-status" role="status">
      <strong>{state.validated ? 'Configuration validated' : 'Configuration not validated'}</strong>
      <span>Sign-in not tested</span>
    </div>
    {#if state.pending === 'loading'}<p role="status">Loading saved setup status…</p>{/if}
    {#if state.status?.state.status === 'in_progress'}<p role="status">A setup request is already in progress. Refresh setup status to check its outcome; it will not be repeated automatically.</p>{/if}
    {#if state.policy?.client.kind === 'dynamic_public'}
      <p>Validation may register a public OAuth application at the provider. It does not sign in a user or test personal access. Requests are never retried, and remote registrations are not removed automatically.</p>
    {:else if state.policy}
      <p>Validation checks provider metadata only. Static client credentials are not verified.</p>
    {/if}
    {#if state.status && 'checked_at' in state.status.state}<p>Last checked: <DateTimeView value={state.status.state.checked_at} /></p>{/if}
    {#if state.status?.state.status === 'validated' && state.status.state.result.scope_source === 'not_returned'}<p>The provider did not return registration scopes. Granted scopes are not verified.</p>{/if}
    {#if state.status}<p>{state.discovery ? 'Effective redirect URI' : 'Unvalidated redirect URI'}: <code>{state.discovery?.redirect_uri ?? state.status.redirect_uri}</code></p>{/if}
    {#if state.policy}<p>Configured scopes: <code>{state.policy.requested_scopes.join(' ') || '(none explicitly requested)'}</code></p>{/if}
    <div class="actions">
      <LoadingButton label="Discover settings" loadingLabel="Discovering settings" loading={state.pending === 'discovery'} disabled={state.locked || !state.policy} onclick={state.discover} variant="secondary" />
      <LoadingButton label="Validate setup" loadingLabel="Validating setup" loading={state.pending === 'validation'} disabled={state.locked || !state.policy} onclick={state.validate} />
      {#if state.requiresRefresh}<Button variant="secondary" disabled={Boolean(state.pending)} onclick={state.refresh}>Refresh setup status</Button>{/if}
    </div>
    {#if state.discovery}
      <div class="discovery">
        <p>Approving scopes or an issuer saves an explicit policy change. An effective change unpublishes the server, clears validation and removes users' saved authorizations and pending sign-ins. Group grants and user enablement remain; remote tokens are not revoked.</p>
        <p>Discovered issuer: <code>{state.discovery.issuer_url}</code></p>
        {#if state.policy?.client.kind === 'preconfigured_public' && state.policy.client.issuer_url !== state.discovery.issuer_url}
          <p>Configured issuer: <code>{state.policy.client.issuer_url}</code></p>
          <Button variant="secondary" disabled={!state.canApprove} onclick={state.acceptIssuer}>Accept discovered issuer</Button>
        {/if}
        <fieldset disabled={state.locked}>
          <legend>Advertised scopes</legend>
          {#each state.discovery.available_scopes as scope (scope)}
            <div class="scope"><AdminToggle ariaLabel={`Select scope ${scope}`} checked={state.scopes.includes(scope)} onchange={(event) => state.toggleScope(scope, (event.currentTarget as HTMLInputElement).checked)} /><code>{scope}</code></div>
          {:else}<p>The provider did not advertise scope candidates.</p>{/each}
        </fieldset>
        {#if state.discovery.available_scopes.length && state.policy?.client.kind !== 'preconfigured_confidential'}
          <Button variant="secondary" disabled={!state.canApprove || state.scopes.length === 0} onclick={state.approveSelectedScopes}>Approve selected scopes</Button>
        {/if}
        {#if state.policy?.client.kind === 'preconfigured_confidential'}<p>Use Edit to accept discovered settings. Saving confidential settings requires a fresh client secret.</p>{/if}
      </div>
    {/if}
    {#if state.returnedScopes !== null}
      <div class="admin-message admin-message--warning" role="alert">
        <p>The provider returned different scopes. Configuration is not validated.</p>
        <p>Configured scopes: <code>{state.policy?.requested_scopes.join(' ') || '(none explicitly requested)'}</code></p>
        <p>Provider scopes: <code>{state.returnedScopes.join(' ') || '(none returned)'}</code></p>
        {#if state.policy?.client.kind !== 'preconfigured_confidential'}<Button disabled={!state.canApprove} onclick={state.approveSuggestedScopes}>Approve provider scopes</Button>{/if}
      </div>
    {/if}
    {#if state.message}<p role="alert" class="admin-message">{state.message}</p>{/if}
  {/if}
</section>

<style>
  .setup { display: grid; gap: 1rem; padding: 1.25rem; min-width: 0; }
  h3, p { margin: 0; }
  p { color: var(--admin-muted); line-height: 1.6; }
  code { overflow-wrap: anywhere; }
  .validation-status, .discovery { display: grid; gap: .75rem; }
  .validation-status span { color: var(--admin-muted); }
  .actions { display: flex; flex-wrap: wrap; gap: .75rem; }
  fieldset { border: 1px solid var(--admin-border); border-radius: var(--admin-radius); display: grid; gap: .75rem; min-width: 0; padding: 1rem; }
  legend { color: var(--admin-muted); padding: 0 .25rem; }
  .scope { display: flex; align-items: center; gap: .75rem; }
</style>
