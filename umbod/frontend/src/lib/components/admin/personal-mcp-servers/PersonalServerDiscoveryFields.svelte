<script lang="ts">
  import type { PersonalServerDiscoveryState } from './personal-server-discovery-state.svelte';
  import type { PolicyForm } from './policy-form.svelte';
  import AdminConfigurationField from '../shared/AdminConfigurationField.svelte';
  import Button from '../shared/Button.svelte';
  import Select from '../shared/Select.svelte';
  let { state, form }: { state: PersonalServerDiscoveryState; form: PolicyForm } = $props();
</script>

<div class="discovery">
  {#if state.pending}<p role="status">Discovering OAuth settings…</p>{/if}
  {#if state.issuers.length}
    <Select id="personal-discovery-issuer" label="OAuth issuer" options={state.issuerOptions} value={state.selectedIssuer} onchange={state.selectIssuer} />
  {/if}
  {#if state.failed}
    <p role="alert">{state.failureMessage}</p>
    <div class="actions"><Button variant="secondary" disabled={state.pending} onclick={state.retry}>Retry discovery</Button><Button variant="secondary" onclick={state.configureManually}>Configure manually</Button></div>
  {/if}
  {#if state.automaticRegistrationUnavailable}<p role="status">Automatic registration unavailable — use an existing client</p>{/if}
  {#if state.result}
    <fieldset>
      <legend>{state.scopeSource}</legend>
      {#if state.result.scope_source === 'unavailable'}<p>Scopes unavailable</p>
      {:else if !state.result.available_scopes.length}<p>No scopes advertised</p>{/if}
      {#each state.result.available_scopes as scope (scope)}
        <label><input type="checkbox" checked={state.selectedScopes.includes(scope)} onchange={(event) => state.toggleScope(scope, event.currentTarget.checked)} /> {scope}</label>
      {/each}
    </fieldset>
    <AdminConfigurationField id="personal-custom-scopes" name="customScopes" label="Custom scopes" placeholder="Space-separated scope tokens" value={state.customScopes} oninput={(event) => state.setCustomScopes((event.currentTarget as HTMLInputElement).value)} />
    {#if state.scopeError}<p role="alert">{state.scopeError}</p>{/if}
    <label><input type="checkbox" checked={state.approved} disabled={!!state.scopeError} onchange={(event) => state.approve(event.currentTarget.checked)} /> Approve issuer {state.result.issuer_url} · {state.scopeSummary}</label>
    <Button variant="quiet" disabled={state.pending} onclick={state.retry}>Refresh OAuth settings</Button>
  {:else if state.manual}
    <AdminConfigurationField id="personal-manual-scopes" name="scopes" label="Requested scopes" placeholder="Space-separated scope tokens" value={form.scopes} oninput={(event) => form.set('scopes', (event.currentTarget as HTMLInputElement).value)} />
    <label><input type="checkbox" checked={state.acknowledged} onchange={(event) => state.acknowledge(event.currentTarget.checked)} /> Save without discovered settings</label>
  {/if}
</div>

<style>
  .discovery, fieldset { display: grid; gap: 12px; min-width: 0; }
  fieldset { border: 0; padding: 0; margin: 0; }
  label { overflow-wrap: anywhere; }
  p { margin: 0; }
  .actions { display: flex; gap: 8px; flex-wrap: wrap; }
</style>
