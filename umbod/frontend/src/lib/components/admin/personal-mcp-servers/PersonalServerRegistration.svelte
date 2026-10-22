<script lang="ts">
  import { onDestroy, untrack } from 'svelte';
  import PersonalServerDialog from './PersonalServerDialog.svelte';
  import AdminConfigurationField from '../shared/AdminConfigurationField.svelte';
  import Button from '../shared/Button.svelte';
  import PolicyFields from './PolicyFields.svelte';
  import { captureInvalidSubmission } from './form-validation';
  import type { PersonalServerFormState } from './personal-server-form-state.svelte';
  let { state, close, reload }: { state: PersonalServerFormState; close: () => void; reload: () => void } = $props();
  onDestroy(untrack(() => state.form.clearSecret));
</script>
  <PersonalServerDialog title="Register personal MCP server" titleId="personal-create-title" descriptionId="personal-create-description" {close}>
    <div class="modal-content">
      <p id="personal-create-description">Registration starts unpublished. No discovery, group grants, user enablement or consent is performed.</p>
      {#if state.message}<p role="alert">{state.message}</p>{/if}
      {#if state.blocked}<Button variant="secondary" disabled={state.busy || state.loading} onclick={reload}>Reload servers</Button>{/if}
      <form {@attach captureInvalidSubmission(state.handleNativeInvalid)} onsubmit={(event) => { event.preventDefault(); void state.create(); }}>
        <fieldset disabled={!state.canRegister}>
          <AdminConfigurationField id="personal-name" name="name" label="Server name" required value={state.metadata.name} oninput={(event) => state.setMetadata('name', (event.currentTarget as HTMLInputElement).value)} />
          <AdminConfigurationField id="personal-endpoint" name="endpoint" label="HTTPS MCP endpoint" required value={state.metadata.endpoint} oninput={(event) => state.setMetadata('endpoint', (event.currentTarget as HTMLInputElement).value)} />
          <AdminConfigurationField id="personal-prefix" name="prefix" label="Tool name prefix" required value={state.metadata.prefix} oninput={(event) => state.setMetadata('prefix', (event.currentTarget as HTMLInputElement).value)} />
          <AdminConfigurationField id="personal-description" name="description" label="Capability description" required value={state.metadata.description} oninput={(event) => state.setMetadata('description', (event.currentTarget as HTMLInputElement).value)} />
          <AdminConfigurationField id="personal-path" name="path" label="Registration path identifier" required value={state.metadata.path} helperText="A unique, fixed registration path identifier under /mcp/proxies/. This does not provide a shared proxy connection or authorize execution. Server details cannot be changed later." oninput={(event) => state.setMetadata('path', (event.currentTarget as HTMLInputElement).value)} />
          <PolicyFields form={state.form} idPrefix="personal-registration" />
          <div class="actions"><Button variant="secondary" onclick={close}>Cancel</Button><Button type="submit">Register unpublished server</Button></div>
        </fieldset>
      </form>
    </div>
  </PersonalServerDialog>
<style>
  .modal-content { overflow-y: auto; min-height: 0; padding-top: 8px; }
  fieldset { border: 0; padding: 0; margin: 0; display: grid; gap: 18px; min-width: 0; }
  .actions { display: flex; gap: 12px; flex-wrap: wrap; }
</style>
