<script lang="ts">
  import AdminConfigurationField from '../shared/AdminConfigurationField.svelte';
  import Select from '../shared/Select.svelte';
  import type { SelectOption } from '../shared/select-state.svelte';
  import type { PolicyForm } from './policy-form.svelte';

  const clientOptions: SelectOption[] = [
    { value: 'dynamic_public', label: 'Automatic registration' },
    { value: 'preconfigured_public', label: 'Use an existing client ID' },
    { value: 'preconfigured_confidential', label: 'Use an existing client ID and secret' }
  ];
  const authenticationOptions: SelectOption[] = [
    { value: 'client_secret_basic', label: 'Basic (client_secret_basic)' },
    { value: 'client_secret_post', label: 'POST (client_secret_post)' }
  ];
  let { form, idPrefix }: { form: PolicyForm; idPrefix: string } = $props();
</script>

<div class="fields">
  {#key form.kind}
    <Select id={`${idPrefix}-client-kind`} label="OAuth application setup" options={clientOptions} value={form.kind} onchange={form.setKind} />
  {/key}
  <p>These settings identify Umbod's application, not a user's login method. Users still connect their own accounts.</p>
  {#if form.kind === 'dynamic_public'}
    <p>The provider registers Umbod's application automatically.</p>
  {:else if form.kind === 'preconfigured_public'}
    <p>An administrator provides the client ID of an existing application registered with the provider.</p>
  {:else}
    <p>An administrator provides an existing application's client ID and secret. The secret is not a user's password.</p>
  {/if}
  <AdminConfigurationField id={`${idPrefix}-scopes`} name="scopes" label="Requested scopes" placeholder="Leave empty to use provider defaults" value={form.scopes} oninput={(event) => form.set('scopes', (event.currentTarget as HTMLInputElement).value)} helperText="Choose only the permissions this server needs, using scope names from the provider's documentation. Case-sensitive, unique ASCII scope tokens separated by ordinary spaces. Up to 64 tokens, 256 characters each and 4,096 joined characters. Empty scopes use provider defaults, not a guarantee of no access." />
  {#if form.kind !== 'dynamic_public'}
    <AdminConfigurationField id={`${idPrefix}-issuer`} name="issuer" label="Exact HTTPS issuer URL" type="url" placeholder="https://auth.example.com" value={form.issuer} required oninput={(event) => form.set('issuer', (event.currentTarget as HTMLInputElement).value)} helperText="The OAuth issuer from the provider's documentation, which may differ from the MCP endpoint. Preserve the provider's exact issuer spelling. No query, fragment or credentials." />
    <AdminConfigurationField id={`${idPrefix}-client-id`} name="clientId" label="Client ID" placeholder="Client ID from the provider" helperText="Copy the identifier of the application registered for Umbod with the provider. This is not a user's account ID or access token." value={form.clientId} required oninput={(event) => form.set('clientId', (event.currentTarget as HTMLInputElement).value)} />
  {/if}
  {#if form.kind === 'preconfigured_confidential'}
    {#if form.configured}<p>Client secret configured. The stored value is never displayed.</p>{/if}
    {#key form.method}
      <Select id={`${idPrefix}-auth-method`} label="Token endpoint authentication" options={authenticationOptions} value={form.method} onchange={form.setMethod} />
    {/key}
    <p>Use the token endpoint authentication method required by the provider: Basic sends application credentials in an HTTP header; POST sends them in the request body.</p>
    <AdminConfigurationField id={`${idPrefix}-client-secret`} name="clientSecret" label="Fresh client secret" placeholder="Client secret from the provider" type="password" autocomplete="new-password" required value={form.secret} oninput={(event) => form.set('secret', (event.currentTarget as HTMLInputElement).value)} helperText="Required for every confidential write. Cleared after submission, failure or closing. This identifies Umbod's OAuth application, not a user's account." />
  {/if}
</div>

<style>
  .fields { display: grid; gap: 12px; min-width: 0; }
  p { color: var(--admin-muted); font-size: 13px; margin: 0; }
</style>
