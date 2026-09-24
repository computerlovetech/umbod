<script lang="ts">
  import type { SubmitFunction } from '@sveltejs/kit';
  import type { DownstreamMcpConnector } from '$lib/admin/downstream-mcp-connectors';
  import AdminConfigurationField from '$lib/components/admin/shared/AdminConfigurationField.svelte';
  import AdminModalShell from '$lib/components/admin/shared/AdminModalShell.svelte';
  import Form from '$lib/components/admin/shared/Form.svelte';
  import LoadingButton from '$lib/components/admin/shared/LoadingButton.svelte';
  import Select from '$lib/components/admin/shared/Select.svelte';
  import type { SelectOption } from '$lib/components/admin/shared/select-state.svelte';
  import type { DownstreamMcpCreateValues, DownstreamMcpWorkspaceState } from './downstream-mcp-workspace-state.svelte';
  import { useToast } from '$lib/components/feedback';

  let { state, connector, message, values }: { state: DownstreamMcpWorkspaceState; connector?: DownstreamMcpConnector; message?: string; values?: DownstreamMcpCreateValues } = $props();
  const configuring = $derived(state.modal === 'configure');
  const toast = useToast();
  const fieldPrefix = $derived(`downstream-mcp-${configuring ? 'configure' : 'create'}`);
  const authenticationOptions: SelectOption[] = [
    { value: 'none', label: 'None' },
    { value: 'static_bearer', label: 'Static token' }
  ];
  const headerTypeOptions: SelectOption[] = [
    { value: 'bearer', label: 'Bearer' },
    { value: 'basic', label: 'Basic' },
    { value: 'custom', label: 'Custom header' }
  ];

  function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }

  const submit: SubmitFunction = () => {
    state.beginSubmit();
    const wasConfiguring = configuring;
    return async ({ result, update }) => {
      if (result.type === 'redirect') {
        toast.success(wasConfiguring ? 'Connector configuration saved' : 'MCP proxy connector added');
      } else if (result.type === 'failure') {
        if (!isRecord(result.data) || !['invalid', 'failed', 'network', 'stale', 'conflict', 'authentication'].includes(String(result.data.status)) || typeof result.data.message !== 'string') {
          throw new Error('Invalid MCP proxy connector setup result');
        }
        if (result.data.status === 'failed' || result.data.status === 'network') toast.error(result.data.message);
      } else {
        throw new Error('Unexpected MCP proxy connector setup result');
      }
      await update();
      if (result.type === 'failure') state.finishSubmit();
    };
  };
</script>

<svelte:window onkeydown={state.handleKeydown} />
{#if state.modal === 'create' || state.modal === 'configure'}
  <AdminModalShell title={configuring ? 'Configure MCP proxy connector' : 'Add MCP proxy connector'} titleId={`${fieldPrefix}-title`} close={state.close}>
    {#snippet children()}
      {#snippet fields()}
        {#if configuring}<input type="hidden" name="connectorId" value={connector?.connector_id ?? ''} />{/if}
        <AdminConfigurationField id={`${fieldPrefix}-display-name`} name="displayName" label="Display name" value={connector?.display_name ?? values?.displayName ?? ''} oninput={configuring ? undefined : state.updateDisplayName} required />
        <AdminConfigurationField id={`${fieldPrefix}-tool-name-prefix`} name="toolNamePrefix" label="Tool name prefix" value={values?.toolNamePrefix ?? state.toolNamePrefix} oninput={state.updateToolNamePrefix} required />
        <AdminConfigurationField id={`${fieldPrefix}-capability-description`} name="capabilityDescription" label="Default capability description" value={connector?.capability_description ?? values?.capabilityDescription ?? ''} helperText="Describes this connector to agents. You can customize the agent-facing description after creation." required />
        <AdminConfigurationField id={`${fieldPrefix}-endpoint`} name="endpointUrl" label="Downstream endpoint" type="url" value={connector?.endpoint_url ?? values?.endpointUrl ?? ''} placeholder="https://mcp.example.com/mcp" required />
        <p class="endpoint-help"><strong>Shared endpoint:</strong> After discovery, enable and publish tools to make them available on <code>/mcp</code>, namespaced with tools from other connectors.</p>
        <div class="path-field">
          <label for={`${fieldPrefix}-public-path`}>Dedicated MCP path (additional)</label>
          <div class:invalid={Boolean(message)} class="path-input">
            <span aria-hidden="true">/mcp/proxies/</span>
            <input
              id={`${fieldPrefix}-public-path`}
              name="publicPath"
              value={configuring ? connector?.public_path.slice('/mcp/proxies/'.length) ?? '' : state.createPublicPath}
              oninput={configuring ? undefined : state.updatePublicPath}
              pattern="[a-z0-9][a-z0-9-]&#123;0,62&#125;"
              maxlength="63"
              required
              readonly={configuring}
              aria-describedby={`${fieldPrefix}-path-helper${message ? ` ${fieldPrefix}-error` : ''}`}
              aria-invalid={Boolean(message) || undefined}
            />
          </div>
          <p class="helper" id={`${fieldPrefix}-path-helper`}>Enter only the connector-specific suffix. Enabled tools can still be published on the shared <code>/mcp</code> endpoint.</p>
        </div>
        <Select id={`${fieldPrefix}-authentication`} label="Authentication" accessibleName="Authentication" options={authenticationOptions} value={state.authMode} onchange={state.setAuthMode} />
        <input type="hidden" name="authMode" value={state.authMode} />
        {#if state.authMode === 'static_bearer'}
          <Select id={`${fieldPrefix}-header-type`} label="Header type" accessibleName="Header type" options={headerTypeOptions} value={state.headerType} onchange={state.setHeaderType} />
          <input type="hidden" name="headerType" value={state.headerType} />
          {#if state.headerType === 'custom'}
            <AdminConfigurationField id={`${fieldPrefix}-custom-header-name`} name="customHeaderName" label="Custom header name" value={state.customHeaderName} oninput={state.updateCustomHeaderName} required />
          {/if}
          <AdminConfigurationField id={`${fieldPrefix}-bearer-token`} name="bearerToken" label="Token" type="password" autocomplete="new-password" required configuredSecret={configuring && Boolean(connector?.credential_configured)} />
        {/if}
        {#if configuring}<p class="warning">Changing the endpoint or authentication unpublishes this connector and requires discovery to run again. The dedicated MCP path is immutable and remains additional to the shared <code>/mcp</code> endpoint.</p>{/if}
        {#if message}<p class="error" id={`${fieldPrefix}-error`} role="alert">{message}</p>{/if}
      {/snippet}
      {#snippet actions()}
        <LoadingButton label="Cancel" loading={false} variant="secondary" onclick={state.close} />
        <LoadingButton type="submit" label="Save connector" loadingLabel="Saving…" loading={state.submitting} />
      {/snippet}
      <Form method="POST" action={configuring ? '?/configure' : '?/create'} {submit} {fields} {actions} />
    {/snippet}
  </AdminModalShell>
{/if}

<style>
  .endpoint-help { color: #5f5e5b; font-size: 12px; margin: 0; }
  .endpoint-help code { color: #37352f; }
  .path-field { display: grid; gap: 7px; }
  .path-field label { color: #37352f; font-size: 13px; font-weight: 650; line-height: 1.4; }
  .path-input { align-items: stretch; background: #fff; border: 1px solid #d9d9d6; border-radius: 8px; display: flex; overflow: hidden; }
  .path-input:focus-within { border-color: #787774; outline: 3px solid rgb(55 53 47 / 12%); }
  .path-input.invalid { border-color: #9f2d20; }
  .path-input span { align-items: center; background: #f1f1ef; border-right: 1px solid #d9d9d6; color: #787774; display: flex; font-size: 14px; padding: 9px 10px; white-space: nowrap; }
  .path-input input { border: 0; color: #37352f; flex: 1; font: inherit; font-size: 14px; line-height: 1.4; min-width: 0; padding: 9px 10px; }
  .path-input input:focus { outline: 0; }
  .path-input input:read-only { background: #f7f7f5; color: #787774; }
  .helper { color: #787774; font-size: 13px; line-height: 1.5; margin: 0; }
  .warning { background: #fff4e8; border-radius: 8px; color: #80521f; font-size: 12px; margin: 0; padding: .7rem; }
  .error { background: #fbe9e7; color: #9f2d20; font-size: 12px; margin: 0; padding: .7rem; }
</style>
