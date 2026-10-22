<script lang="ts">
  import AdminConfigurationField from '../shared/AdminConfigurationField.svelte';
  import type { PolicyForm } from './policy-form.svelte';
  let { form }: { form: PolicyForm } = $props();
</script>

<div class="fields">
  <label for="personal-client-kind">OAuth client</label>
  <select id="personal-client-kind" value={form.kind} onchange={(event) => form.setKind(event.currentTarget.value)}>
    <option value="dynamic_public">Dynamic public</option>
    <option value="preconfigured_public">Preconfigured public</option>
    <option value="preconfigured_confidential">Preconfigured confidential</option>
  </select>
  <AdminConfigurationField id="personal-scopes" name="scopes" label="Requested scopes" value={form.scopes} oninput={(event) => form.set('scopes', (event.currentTarget as HTMLInputElement).value)} helperText="Case-sensitive, unique ASCII scope tokens separated by ordinary spaces. Up to 64 tokens, 256 characters each and 4,096 joined characters. Empty scopes use provider defaults, not a guarantee of no access." />
  {#if form.kind !== 'dynamic_public'}
    <AdminConfigurationField id="personal-issuer" name="issuer" label="Exact HTTPS issuer URL" value={form.issuer} required oninput={(event) => form.set('issuer', (event.currentTarget as HTMLInputElement).value)} helperText="Preserve the provider's exact issuer spelling. No query, fragment or credentials." />
    <AdminConfigurationField id="personal-client-id" name="clientId" label="Client ID" value={form.clientId} required oninput={(event) => form.set('clientId', (event.currentTarget as HTMLInputElement).value)} />
  {/if}
  {#if form.kind === 'preconfigured_confidential'}
    {#if form.configured}<p>Client secret configured. The stored value is never displayed.</p>{/if}
    <label for="personal-auth-method">Token endpoint authentication</label>
    <select id="personal-auth-method" value={form.method} onchange={(event) => form.setMethod(event.currentTarget.value)}>
      <option value="client_secret_basic">Basic (client_secret_basic)</option>
      <option value="client_secret_post">POST (client_secret_post)</option>
    </select>
    <AdminConfigurationField id="personal-client-secret" name="clientSecret" label="Fresh client secret" type="password" autocomplete="new-password" required value={form.secret} oninput={(event) => form.set('secret', (event.currentTarget as HTMLInputElement).value)} helperText="Required for every confidential write. Cleared after submission, failure or closing. This identifies Umbod's OAuth application, not a user's account." />
  {/if}
</div>

<style>
  .fields { display: grid; gap: 12px; min-width: 0; }
  label { color: var(--admin-ink); font-size: 13px; font-weight: 650; }
  select { background: var(--admin-panel); border: 1px solid var(--admin-border-strong); border-radius: var(--admin-radius); color: var(--admin-ink); font: inherit; padding: 10px; width: 100%; }
  p { color: var(--admin-muted); font-size: 13px; margin: 0; }
</style>
