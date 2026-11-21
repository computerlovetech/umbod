<script lang="ts">
  import type { BrowserSubmitFunction as SubmitFunction } from '#lib/admin/operations/browser-submit.js';
  import AdminConfigurationField from '#lib/components/admin/shared/AdminConfigurationField.svelte';
  import AdminFileUpload from '#lib/components/admin/shared/AdminFileUpload.svelte';
  import ModalShell from '#lib/components/shared/ModalShell.svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import SetupProgress from '#lib/components/admin/shared/SetupProgress.svelte';
  import Form from '#lib/components/admin/shared/Form.svelte';
  import LoadingButton from '#lib/components/admin/shared/LoadingButton.svelte';
  import Select from '#lib/components/admin/shared/Select.svelte';
  import type { SelectOption } from '#lib/components/admin/shared/select-state.svelte.js';
  import type { OpenApiConnectorSetupState } from './openapi-connector-setup-state.svelte';

  let { state }: { state: OpenApiConnectorSetupState } = $props();

  const steps = ['Specification', 'API server', 'Configure'];

  function reviewSource(event: SubmitEvent): void {
    event.preventDefault();
    if (event.currentTarget instanceof HTMLFormElement) void state.reviewSource(new FormData(event.currentTarget));
  }

  function confirmHostname(event: SubmitEvent): void {
    event.preventDefault();
    state.confirmHostname();
  }

  function focusHeading(heading: HTMLElement): void {
    heading.focus({ preventScroll: true });
  }

  const authenticationOptions: SelectOption[] = [
    { value: 'none', label: 'None' },
    { value: 'bearer', label: 'Bearer token' }
  ];

  const submit: SubmitFunction = async ({ formData, cancel, onComplete }) => {
    const session = state.session;
    onComplete(() => {
      if (state.session === session) state.completeSubmit(null);
    });
    state.beginSubmit();
    if (!(await state.prepareSubmission(formData)) || state.session !== session) {
      cancel();
      return;
    }
    return async ({ result, update }) => {
      if (state.session === session) state.completeSubmit(result);
      await update({ reset: false });
    };
  };
</script>

<svelte:window onkeydown={state.handleKeydown} />

{#if state.open}
  <ModalShell title={state.mode === 'create' ? 'Add OpenAPI connector' : 'Configure OpenAPI connector'} titleId="openapi-setup-title" close={state.close}
    initialFocus={state.mode === 'create' ? '[data-dialog-title]' : undefined}
    --modal-title-focus-outline={state.mode === 'create' ? 'none' : undefined}
    --modal-overflow={state.mode === 'create' ? 'auto' : undefined}
    --modal-width={state.mode === 'create' ? '39rem' : undefined}
    --modal-background={state.mode === 'create' ? 'linear-gradient(135deg, var(--admin-accent-soft), var(--admin-panel) 17rem)' : undefined}
    --admin-radius-panel={state.mode === 'create' ? '24px' : undefined}>
    {#snippet children()}
      {#snippet identityFields()}
        <input type="hidden" name="connectorId" value={state.connectorId} />
        <AdminConfigurationField id="openapi-setup-display-name" name="displayName" label="Display name" value={state.displayName} maxlength={200} required readonly={state.mode === 'configure'} oninput={state.setDisplayName} />
        <AdminConfigurationField id="openapi-setup-tool-name-prefix" name="toolNamePrefix" label="Tool name prefix" value={state.toolNamePrefix} required readonly={state.mode === 'configure'} oninput={state.setToolNamePrefix} />
        <AdminConfigurationField id="openapi-setup-capability-description" name="capabilityDescription" label="Capability description" value={state.capabilityDescription} maxlength={300} required readonly={state.mode === 'configure'} oninput={state.setCapabilityDescription} />
        <Select id="openapi-setup-authentication" label="Authentication" accessibleName="Authentication" options={authenticationOptions} value={state.authenticationType} onchange={state.setAuthentication} />
        <input type="hidden" name="authenticationType" value={state.authenticationType} />
        {#if state.authenticationType === 'bearer'}
          <AdminConfigurationField id="openapi-setup-bearer" name="bearerToken" label="Bearer token" type="password" autocomplete="new-password" required={state.mode === 'create'} configuredSecret={state.mode === 'configure' && state.configuredBearer} />
        {/if}
      {/snippet}
      {#snippet sourceFields()}
        {#if state.mode === 'create'}
          <div class="source-tiles" role="group" aria-label="OpenAPI specification source">
            <Button type="button" class="source-tile" variant="secondary" disabled={state.submitting} aria-pressed={state.importMode === 'file'} onclick={() => state.setImportMode('file')}>
              <span class="source-icon" aria-hidden="true"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M6 3h8l4 4v14H6z M14 3v5h4 M9 12h6 M9 16h6" /></svg></span>
              Upload JSON file
            </Button>
            <Button type="button" class="source-tile" variant="secondary" disabled={state.submitting} aria-pressed={state.importMode === 'url'} onclick={() => state.setImportMode('url')}>
              <span class="source-icon" aria-hidden="true"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="m10 13 4-4 M9 16l-2 2a3.5 3.5 0 0 1-5-5l4-4a3.5 3.5 0 0 1 5 0 M13 8l2-2a3.5 3.5 0 0 1 5 5l-4 4a3.5 3.5 0 0 1-5 0" /></svg></span>
              Enter HTTPS URL
            </Button>
          </div>
        {:else}
          <div class="import-tabs" role="group" aria-label="OpenAPI specification source">
            <button type="button" class:active={state.importMode === 'file'} aria-pressed={state.importMode === 'file'} onclick={() => state.setImportMode('file')}>File</button>
            <button type="button" class:active={state.importMode === 'url'} aria-pressed={state.importMode === 'url'} onclick={() => state.setImportMode('url')}>HTTPS URL</button>
          </div>
        {/if}
        {#if state.importMode === 'file'}
          <AdminFileUpload
            id="openapi-setup-file"
            name="file"
            label="OpenAPI JSON specification file"
            optionalText={state.mode === 'configure' ? '(optional)' : ''}
            accept="application/json,.json"
            required={state.mode === 'create'}
            disabled={state.mode === 'create' && state.submitting}
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
            readonly={state.mode === 'create' && state.submitting}
            oninput={state.setSpecificationUrl}
          />
          <p class="helper">The document is retrieved directly from an HTTPS URL.</p>
        {/if}
        {#if state.urlError}<p class="error" role="alert">{state.urlError}</p>{/if}
      {/snippet}
      {#snippet hostnameField()}
        <AdminConfigurationField id="openapi-setup-hostname" name="approvedHostname" label="Approved hostname" value={state.approvedHostname} required={state.mode === 'create'} oninput={state.setHostname} />
        <p class="helper">Enter an exact hostname, such as api.example.com.</p>
      {/snippet}
      {#snippet fields()}
        {#if state.mode === 'create' && state.step === 3}
          <h3 tabindex="-1" {@attach focusHeading}>Configure and save</h3>
        {/if}
        {@render identityFields()}
        {#if state.mode === 'configure'}
          {@render sourceFields()}
          {@render hostnameField()}
        {/if}
        {#if state.message}<p class="error" role="alert">{state.message}</p>{/if}
      {/snippet}
      {#snippet actions()}
        {#if state.mode === 'create'}
          <Button type="button" variant="quiet" disabled={state.submitting || state.setupBlocked} onclick={state.back}>Back</Button>
        {:else}
          <LoadingButton label="Cancel" loading={false} variant="secondary" onclick={state.close} />
        {/if}
        <LoadingButton type="submit" label="Save" loadingLabel="Saving…" loading={state.submitting} disabled={state.setupBlocked} />
      {/snippet}
      {#if state.mode === 'create'}
        <SetupProgress {steps} current={state.step} />
        <div hidden={state.step !== 1} inert={state.step !== 1}>
          <form class="stage" onsubmit={reviewSource}>
            <h3>Add a specification</h3>
            {@render sourceFields()}
            <div class="stage-actions"><LoadingButton type="submit" label="Next" loadingLabel="Reading specification…" loading={state.step === 1 && state.submitting} /></div>
          </form>
        </div>
        {#if state.step === 2}
          <form class="stage" onsubmit={confirmHostname}>
            <h3 tabindex="-1" {@attach focusHeading}>Review the API server</h3>
            {#if state.servers.length}
              <div class="server-evidence">
                <strong>Addresses declared in the specification</strong>
                <ul>{#each state.servers as server (server)}<li>{server}</li>{/each}</ul>
                {#if !state.hostnameValid}<p class="host-hint">Approve a hostname that matches exactly one address. If the same hostname appears on multiple server entries, edit the specification to keep just one of them.</p>{/if}
              </div>
            {/if}
            {@render hostnameField()}
            <div class="stage-actions">
              <Button type="button" variant="quiet" onclick={state.back}>Back</Button>
              <Button type="submit" disabled={!state.hostnameValid}>Next</Button>
            </div>
          </form>
        {/if}
      {/if}
      {#if state.mode === 'configure'}
        <Form method="POST" operation="configure" enctype="multipart/form-data" {submit} {fields} {actions} />
      {:else if state.step >= 2}
        <div hidden={state.step !== 3} inert={state.step !== 3}>
          {#key state.approvedHostname}
            <Form method="POST" operation="setup" enctype="multipart/form-data" {submit} {fields} {actions} />
          {/key}
        </div>
      {/if}
    {/snippet}
  </ModalShell>
{/if}

<style>
  .stage { display: grid; gap: .875rem; }
  h3 { margin: 0; font-size: 1.0625rem; letter-spacing: -.02em; }
  .source-tiles { display: grid; grid-template-columns: repeat(2, minmax(0, 10rem)); gap: .75rem; justify-content: center; }
  .source-tiles :global(.source-tile) { display: grid; place-content: center; justify-items: center; gap: .6rem; aspect-ratio: 1; height: auto; padding: .65rem; white-space: normal; text-align: center; background: var(--admin-soft); border: 1px solid var(--admin-border-strong); border-radius: 20px; }
  .source-tiles :global(.source-tile[aria-pressed='true']), .source-tiles :global(.source-tile:hover) { background: var(--admin-accent-soft); border-color: var(--admin-accent-border); }
  .source-icon { display: grid; place-items: center; width: 2.6rem; aspect-ratio: 1; border: 1px solid var(--admin-accent-border); border-radius: 30%; background: var(--admin-panel); color: var(--admin-accent); }
  .server-evidence { padding: .875rem 1rem; border: 1px solid var(--admin-accent-border); border-radius: var(--admin-radius-panel); background: var(--admin-accent-soft); overflow-wrap: anywhere; }
  .host-hint { margin: .5rem 0 0; font-size: 13px; }
  .server-evidence ul { margin: .35rem 0 0; padding-inline-start: 1.1rem; }
  .stage-actions { display: flex; justify-content: space-between; gap: .75rem; padding-top: 1rem; border-top: 1px solid var(--admin-border); }
  .stage-actions > :only-child { margin-inline-start: auto; }
  .import-tabs { border-bottom: 1px solid var(--admin-border-strong); display: flex; gap: 18px; }
  .import-tabs button { background: transparent; border: 0; border-bottom: 2px solid transparent; color: var(--admin-muted); cursor: pointer; font: inherit; font-size: 13px; font-weight: 650; padding: 0 2px 8px; }
  .import-tabs button.active { border-bottom-color: var(--admin-ink); color: var(--admin-ink); }
  .helper { color: var(--admin-muted); font-size: 13px; margin: -0.5rem 0 0; }
  .error { background: var(--admin-danger-bg); border-radius: 8px; color: var(--admin-danger-text); font-size: 13px; margin: 0; padding: 9px 10px; }
</style>
