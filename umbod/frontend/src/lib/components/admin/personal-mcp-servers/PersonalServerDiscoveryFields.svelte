<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { PersonalServerDiscoveryState } from './personal-server-discovery-state.svelte';
  import type { PolicyForm } from './policy-form.svelte';
  import Checkbox from '$lib/components/shared/Checkbox.svelte';
  import AdminConfigurationField from '../shared/AdminConfigurationField.svelte';
  import Button from '../shared/Button.svelte';
  import Select from '../shared/Select.svelte';
  let { state, form, clientSetup }: { state: PersonalServerDiscoveryState; form: PolicyForm; clientSetup: Snippet } = $props();
</script>

<div class="discovery">
  <section class="step" aria-labelledby="personal-discovery-heading">
    <span class={['step-dot', { completed: !!state.result && !state.pending && !state.failed }]} aria-hidden="true">{state.result && !state.pending && !state.failed ? '✓' : '1'}</span>
    <div class="step-content">
      <h3 id="personal-discovery-heading">Discover OAuth settings</h3>
      {#if state.pending}<p role="status">Discovering OAuth settings…</p>{/if}
      {#if state.issuers.length}
        <Select id="personal-discovery-issuer" label="OAuth issuer" options={state.issuerOptions} value={state.selectedIssuer} onchange={state.selectIssuer} />
      {/if}
      {#if state.failed}
        <p role="alert">{state.failureMessage}</p>
        <div class="actions"><Button variant="secondary" disabled={state.pending} onclick={state.retry}>Retry discovery</Button><Button variant="secondary" onclick={state.configureManually}>Configure manually</Button></div>
      {:else if state.result}
        <p role="status">Discovery complete</p>
        <p class="issuer">From <code>{state.result.issuer_url}</code></p>
        <Button variant="quiet" disabled={state.pending} onclick={state.retry}>Refresh OAuth settings</Button>
      {:else if !state.pending && !state.issuers.length}
        <p>Enter the MCP endpoint above to discover its OAuth settings.</p>
      {/if}
    </div>
  </section>
  <section class="step" aria-labelledby="personal-permissions-heading">
    <span class={['step-dot', { completed: !!state.result && state.approved && !state.scopeError }]} aria-hidden="true">{state.result && state.approved && !state.scopeError ? '✓' : '2'}</span>
    <div class="step-content">
      <h3 id="personal-permissions-heading">Review discovered permissions</h3>
      {#if state.result}
        <fieldset>
          <legend>{state.scopeSource}</legend>
          {#if state.result.scope_source === 'unavailable'}<p>Scopes unavailable</p>
          {:else if !state.result.available_scopes.length}<p>No scopes advertised</p>{/if}
          {#each state.result.available_scopes as scope (scope)}
            <Checkbox id={`personal-discovered-scope-${scope}`} label={scope} checked={state.selectedScopes.includes(scope)} onchange={(event: Event): void => state.toggleScope(scope, (event.currentTarget as HTMLInputElement).checked)} />
          {/each}
        </fieldset>
        <AdminConfigurationField id="personal-custom-scopes" name="customScopes" label="Custom scopes" placeholder="Space-separated scope tokens" value={state.customScopes} oninput={(event: Event): void => state.setCustomScopes((event.currentTarget as HTMLInputElement).value)} />
        {#if state.scopeError}<p role="alert">{state.scopeError}</p>{/if}
      {:else if state.manual}
        <AdminConfigurationField id="personal-manual-scopes" name="scopes" label="Requested scopes" placeholder="Space-separated scope tokens" value={form.scopes} oninput={(event: Event): void => form.set('scopes', (event.currentTarget as HTMLInputElement).value)} />
      {:else}
        <p>{state.failed ? 'Scopes unavailable. Retry discovery or configure manually.' : 'Permissions will appear after discovery.'}</p>
      {/if}
    </div>
  </section>
  <section class="step" aria-labelledby="personal-client-heading">
    <span class="step-dot" aria-hidden="true">3</span>
    <div class="step-content">
      <h3 id="personal-client-heading">Set up OAuth application</h3>
      {#if state.result && state.automaticRegistrationUnavailable}
        <p>Umbod cannot automatically register an application with this provider. You can use an existing OAuth application instead.</p>
      {/if}
      {@render clientSetup()}
      {#if state.result}
        <p id="personal-discovery-summary" class="issuer">Issuer: <code>{state.result.issuer_url}</code> · {state.scopeSummary}</p>
        <Checkbox id="personal-discovery-approval" label="Approve issuer and selected permissions" aria-describedby="personal-discovery-summary" checked={state.approved} disabled={!!state.scopeError} onchange={(event: Event): void => state.approve((event.currentTarget as HTMLInputElement).checked)} />
      {:else if state.manual}
        <Checkbox id="personal-manual-acknowledgement" label="Save without discovered settings" checked={state.acknowledged} onchange={(event: Event): void => state.acknowledge((event.currentTarget as HTMLInputElement).checked)} />
      {/if}
    </div>
  </section>
</div>

<style>
  .discovery, .step-content, fieldset { display: grid; gap: 12px; min-width: 0; }
  .discovery { gap: 0; }
  .step { position: relative; display: grid; grid-template-columns: 28px minmax(0, 1fr); gap: 12px; padding-bottom: 24px; }
  .step:not(:last-child)::before { content: ''; position: absolute; top: 28px; bottom: 0; left: 13px; border-left: 1px solid var(--admin-border); }
  .step:last-child { padding-bottom: 0; }
  .step-dot { display: grid; place-items: center; width: 28px; height: 28px; border: 1px solid var(--admin-border-strong); border-radius: 50%; color: var(--admin-muted); font-size: 12px; }
  .step-dot.completed { background: var(--admin-success-bg); border-color: var(--admin-success-border); color: var(--admin-success-text); }
  h3 { margin: 4px 0 0; font-size: 0.95rem; color: var(--admin-ink); }
  fieldset { border: 0; padding: 0; margin: 0; }
  legend { margin-bottom: 10px; }
  p { margin: 0; color: var(--admin-muted); font-size: 13px; }
  .issuer { overflow-wrap: anywhere; }
  .actions { display: flex; gap: 8px; flex-wrap: wrap; }
</style>
