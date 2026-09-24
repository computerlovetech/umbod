<script lang="ts">
  import type { SubmitFunction } from '@sveltejs/kit';
  import AdminConfigurationField from '$lib/components/admin/shared/AdminConfigurationField.svelte';
  import AdminFileUpload from '$lib/components/admin/shared/AdminFileUpload.svelte';
  import AdminModalShell from '$lib/components/admin/shared/AdminModalShell.svelte';
  import Form from '$lib/components/admin/shared/Form.svelte';
  import LoadingButton from '$lib/components/admin/shared/LoadingButton.svelte';
  import Select from '$lib/components/admin/shared/Select.svelte';
  import type { SelectOption } from '$lib/components/admin/shared/select-state.svelte';
  import type { OpenApiConnectorSetupState } from './openapi-connector-setup-state.svelte';

  let { state }: { state: OpenApiConnectorSetupState } = $props();

  const authenticationOptions: SelectOption[] = [
    { value: 'none', label: 'None' },
    { value: 'bearer', label: 'Bearer token' }
  ];

  const submit: SubmitFunction = async ({ formData, cancel }) => {
    state.beginSubmit();
    if (!(await state.prepareSubmission(formData))) {
      cancel();
      state.completeSubmit(null);
      return;
    }
    return async ({ result, update }) => {
      state.completeSubmit(result);
      await update({ reset: false });
    };
  };
</script>

<svelte:window onkeydown={state.handleKeydown} />

{#if state.open}
  <AdminModalShell title={state.mode === 'create' ? 'Add OpenAPI connector' : 'Configure OpenAPI connector'} titleId="openapi-setup-title" close={state.close}>
    {#snippet children()}
      {#snippet fields()}
        <input type="hidden" name="connectorId" value={state.connectorId} />
        <AdminConfigurationField id="openapi-setup-display-name" name="displayName" label="Display name" value={state.displayName} required readonly={state.mode === 'configure'} oninput={state.setDisplayName} />
        <AdminConfigurationField id="openapi-setup-tool-name-prefix" name="toolNamePrefix" label="Tool name prefix" value={state.toolNamePrefix} required readonly={state.mode === 'configure'} oninput={state.setToolNamePrefix} />
        <AdminConfigurationField id="openapi-setup-capability-description" name="capabilityDescription" label="Capability description" value={state.capabilityDescription} required readonly={state.mode === 'configure'} />
        <Select id="openapi-setup-authentication" label="Authentication" accessibleName="Authentication" options={authenticationOptions} value={state.authenticationType} onchange={state.setAuthentication} />
        <input type="hidden" name="authenticationType" value={state.authenticationType} />
        {#if state.authenticationType === 'bearer'}
          <AdminConfigurationField id="openapi-setup-bearer" name="bearerToken" label="Bearer token" type="password" autocomplete="new-password" required={state.mode === 'create'} configuredSecret={state.mode === 'configure' && state.configuredBearer} />
        {/if}
        <div class="import-tabs" role="group" aria-label="OpenAPI specification source">
          <button type="button" class:active={state.importMode === 'file'} aria-pressed={state.importMode === 'file'} onclick={() => state.setImportMode('file')}>File</button>
          <button type="button" class:active={state.importMode === 'url'} aria-pressed={state.importMode === 'url'} onclick={() => state.setImportMode('url')}>HTTPS URL</button>
        </div>
        {#if state.importMode === 'file'}
          <AdminFileUpload
            id="openapi-setup-file"
            name="file"
            label="OpenAPI JSON specification file"
            optionalText={state.mode === 'configure' ? '(optional)' : ''}
            accept="application/json,.json"
            required={state.mode === 'create'}
            buttonText="Choose JSON file"
            helperText="JSON · Maximum 10 MB"
            maxBytes={10 * 1024 * 1024}
          />
        {:else}
          <AdminConfigurationField
            id="openapi-setup-url"
            name="url"
            label={`OpenAPI JSON specification URL${state.mode === 'configure' ? ' (optional)' : ''}`}
            value={state.specificationUrl}
            required={state.mode === 'create'}
            oninput={state.setSpecificationUrl}
          />
          <p class="helper">The document is retrieved directly from an HTTPS URL.</p>
          {#if state.urlError}<p class="error" role="alert">{state.urlError}</p>{/if}
        {/if}
        <AdminConfigurationField id="openapi-setup-hostname" name="approvedHostname" label="Approved hostname" value={state.approvedHostname} required={state.mode === 'create'} oninput={state.setHostname} />
        <p class="helper">Enter an exact hostname, such as api.example.com.</p>
        {#if state.message}<p class="error" role="alert">{state.message}</p>{/if}
      {/snippet}
      {#snippet actions()}
        <LoadingButton label="Cancel" loading={false} variant="secondary" onclick={state.close} />
        <LoadingButton type="submit" label="Save" loadingLabel="Saving…" loading={state.submitting} />
      {/snippet}
      <Form method="POST" action={state.mode === 'create' ? '?/setup' : '?/configure'} enctype="multipart/form-data" {submit} {fields} {actions} />
    {/snippet}
  </AdminModalShell>
{/if}

<style>
  .import-tabs { border-bottom: 1px solid #d9d9d6; display: flex; gap: 18px; }
  .import-tabs button { background: transparent; border: 0; border-bottom: 2px solid transparent; color: #787774; cursor: pointer; font: inherit; font-size: 13px; font-weight: 650; padding: 0 2px 8px; }
  .import-tabs button.active { border-bottom-color: #37352f; color: #37352f; }
  .helper { color: #787774; font-size: 13px; margin: -0.5rem 0 0; }
  .error { background: #fbe9e7; border-radius: 8px; color: #9f2d20; font-size: 13px; margin: 0; padding: 9px 10px; }
</style>
