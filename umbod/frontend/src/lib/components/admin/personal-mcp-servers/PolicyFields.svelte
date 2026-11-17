<script lang="ts">
  import type { Snippet } from 'svelte';
  import AdminConfigurationField from '../shared/AdminConfigurationField.svelte';
  import Select from '../shared/Select.svelte';
  import type { SelectOption } from '../shared/select-state.svelte';
  import type { PolicyForm, PolicyProposal } from './policy-form.svelte';
  import Button from '../shared/Button.svelte';

  const clientOptions: SelectOption[] = [
    { value: 'automatic', label: 'Automatic registration' },
    { value: 'preconfigured_public', label: 'Use an existing client ID' },
    { value: 'preconfigured_confidential', label: 'Use an existing client ID and secret' }
  ];
  const authenticationOptions: SelectOption[] = [
    { value: 'client_secret_basic', label: 'Basic (client_secret_basic)' },
    { value: 'client_secret_post', label: 'POST (client_secret_post)' }
  ];
  let { form, idPrefix, proposal, scopes, discoveredIssuer, onClientSelection }: { form: PolicyForm; idPrefix: string; proposal?: PolicyProposal; scopes?: Snippet; discoveredIssuer?: string; onClientSelection?: (value: string) => void | Promise<void> } = $props();
</script>

<div class="fields">
  <Select id={`${idPrefix}-client-kind`} label="OAuth application setup" options={clientOptions} value={form.clientSelection} onchange={onClientSelection ?? form.setKind} />
  {#if proposal}<p>Discovered issuer: <code>{proposal.issuer}</code></p><Button variant="secondary" onclick={(): void => form.set('issuer', proposal!.issuer)}>Use discovered issuer</Button>{/if}
  {#if !form.automatic}
    <AdminConfigurationField id={`${idPrefix}-issuer`} name="issuer" label="Exact HTTPS issuer URL" type="url" placeholder="https://auth.example.com" readonly={!!discoveredIssuer} value={discoveredIssuer ?? form.issuer} required oninput={(event) => form.set('issuer', (event.currentTarget as HTMLInputElement).value)} />
  {/if}
  {#if !form.automatic}
    <AdminConfigurationField id={`${idPrefix}-client-id`} name="clientId" label="Client ID" placeholder="Client ID from the provider" value={form.clientId} required oninput={(event) => form.set('clientId', (event.currentTarget as HTMLInputElement).value)} />
  {/if}
  {#if form.automatic && form.automaticSupported}
    <p>Application credentials will be obtained automatically when a user connects. Each user signs in with their own account.</p>
  {/if}
  {#if form.kind === 'preconfigured_confidential'}
    {#if form.configured}<p>Client secret configured. Enter a fresh secret to save.</p>{/if}
    <Select id={`${idPrefix}-auth-method`} label="Token endpoint authentication" options={authenticationOptions} value={form.method} onchange={form.setMethod} />
    <AdminConfigurationField id={`${idPrefix}-client-secret`} name="clientSecret" label="Fresh client secret" placeholder="Client secret from the provider" type="password" autocomplete="new-password" required value={form.secret} oninput={(event) => form.set('secret', (event.currentTarget as HTMLInputElement).value)} />
  {/if}
  {#if scopes}
    {@render scopes()}
  {:else}
    <AdminConfigurationField id={`${idPrefix}-scopes`} name="scopes" label="Requested scopes" placeholder="Space-separated scope tokens" value={form.scopes} oninput={(event) => form.set('scopes', (event.currentTarget as HTMLInputElement).value)} />
    {#if proposal?.scopes.length}<Button variant="secondary" onclick={() => form.set('scopes', proposal!.scopes.join(' '))}>Use selected scopes</Button>{/if}
  {/if}
</div>

<style>
  .fields { display: grid; gap: 12px; min-width: 0; }
  p { color: var(--admin-muted); font-size: 13px; margin: 0; }
</style>
