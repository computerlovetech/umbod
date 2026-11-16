<script lang="ts">
  import { onDestroy, untrack } from 'svelte';
  import PersonalServerDialog from './PersonalServerDialog.svelte';
  import AdminConfigurationField from '../shared/AdminConfigurationField.svelte';
  import Button from '../shared/Button.svelte';
  import PolicyFields from './PolicyFields.svelte';
  import { captureInvalidSubmission } from './form-validation';
  import type { PersonalServerFormState } from './personal-server-form-state.svelte';
  import type { PolicyProposal } from './policy-form.svelte';
  let { state, close, reload, proposal }: { state: PersonalServerFormState; close: () => void; reload: () => void; proposal?: PolicyProposal } = $props();
  onDestroy(untrack(() => state.form.clearSecret));
</script>
  <PersonalServerDialog title={state.editing ? "Edit MCP server with personal authorization" : "Register MCP server with personal authorization"} titleId="personal-create-title" descriptionId="personal-create-description" {close}>
    <div class="modal-content">
      <p id="personal-create-description">{state.editing ? "Server details and endpoint are read-only. Update the OAuth application settings below." : "Registration starts unpublished. No discovery, group grants, user enablement or consent is performed."}</p>
      {#if state.message}<p role="alert">{state.message}</p>{/if}
      {#if state.blocked}<Button variant="secondary" disabled={state.busy || state.loading} onclick={reload}>{state.editing ? "Reload OAuth settings" : "Reload servers"}</Button>{/if}
      {#if state.loading}<p role="status">Loading OAuth settings…</p>{/if}
      {#if state.confirmation}
        <section aria-labelledby="personal-confirm-title">
          <h3 id="personal-confirm-title" tabindex="-1" {@attach (element: HTMLHeadingElement): void => element.focus()}>Save OAuth settings?</h3>
          <p>An effective change erases ALL users' saved authorizations and pending sign-ins for this server. The server is unpublished and setup validation is cleared. User enablement and group grants persist. Remote tokens are not revoked. Every confidential save explicitly rotates the client secret.</p>
          <div class="actions"><Button variant="secondary" onclick={state.close}>Back</Button><Button variant="danger" disabled={state.locked} onclick={state.confirm}>Save settings</Button></div>
        </section>
      {:else}
      <form {@attach captureInvalidSubmission(state.handleNativeInvalid)} onsubmit={(event) => { event.preventDefault(); if (state.editing) state.requestConfirmation('policy'); else void state.create(); }}>
        <fieldset disabled={state.editing ? state.locked || !state.policy : !state.canRegister}>
          <div class="section-heading">
            <h3>Server details</h3>
            <p>Your organisation manages the connector; each user authorizes access using their own account. Server details and the endpoint cannot be changed after registration; OAuth settings can be updated separately.</p>
          </div>
          <AdminConfigurationField readonly={state.editing} id="personal-name" name="name" label="Server name" placeholder="Acme MCP" helperText="The name users see in Dashboard. Suggests the tool prefix and registration identifier until you edit them." required value={state.metadata.name} oninput={(event) => state.setMetadata('name', (event.currentTarget as HTMLInputElement).value)} />
          <AdminConfigurationField readonly={state.editing} id="personal-endpoint" name="endpoint" label="HTTPS MCP endpoint" type="url" placeholder="https://mcp.example.com/mcp" helperText="The provider's MCP server address, not its website or OAuth sign-in URL. Use HTTPS without embedded credentials or a fragment." required value={state.metadata.endpoint} oninput={(event) => state.setMetadata('endpoint', (event.currentTarget as HTMLInputElement).value)} />
          <AdminConfigurationField readonly={state.editing} id="personal-prefix" name="prefix" label="Tool name prefix" placeholder="Acme_MCP" pattern="[a-zA-Z0-9_\-]+" helperText="Namespaces this server's tools so agents can distinguish them from other connectors. Use letters, numbers, underscores or hyphens. You can change the suggestion before registering." required value={state.metadata.prefix} oninput={(event) => state.setMetadata('prefix', (event.currentTarget as HTMLInputElement).value)} />
          <AdminConfigurationField readonly={state.editing} id="personal-description" name="description" label="Capability description" placeholder="Search projects and manage tasks in Acme." maxlength={300} helperText="Describes this server's capabilities to agents so they know when to use it. Use plain text, up to 300 characters; do not include credentials." required value={state.metadata.description} oninput={(event) => state.setMetadata('description', (event.currentTarget as HTMLInputElement).value)} />
          <AdminConfigurationField readonly={state.editing} id="personal-path" name="path" label="Registration path identifier" inputPrefix="/mcp/proxies/" placeholder="acme-mcp" pattern="[a-z0-9][a-z0-9\-]&#123;0,62&#125;" maxlength={63} required value={state.metadata.path} helperText="Enter only the unique identifier after /mcp/proxies/. Use 1–63 lowercase letters, numbers or hyphens, starting with a letter or number. Reserved names such as oauth and health are not allowed. Suggestions are not checked for availability. This does not provide a shared proxy connection or authorize execution." oninput={(event) => state.setMetadata('path', (event.currentTarget as HTMLInputElement).value)} />
          <div class="section-heading">
            <h3>OAuth application</h3>
            <p>Choose how Umbod identifies itself to the provider. These settings do not sign users in or grant them access.</p>
          </div>
          <PolicyFields form={state.form} {proposal} idPrefix={state.editing ? "personal-edit" : "personal-registration"} />
          <div class="actions"><Button variant="secondary" onclick={close}>Cancel</Button><Button type="submit">{state.editing ? "Review changes" : "Register unpublished server"}</Button></div>
        </fieldset>
      </form>
      {/if}
    </div>
  </PersonalServerDialog>
<style>
  .modal-content { overflow-y: auto; min-height: 0; padding-top: 8px; }
  fieldset { border: 0; padding: 0; margin: 0; display: grid; gap: 18px; min-width: 0; }
  .actions { display: flex; gap: 12px; flex-wrap: wrap; }
  .section-heading { display: grid; gap: 7px; }
  .section-heading h3 { color: var(--admin-ink); font-size: 1rem; margin: 0; }
  .section-heading p { color: var(--admin-muted); font-size: 13px; line-height: 1.5; margin: 0; }
</style>
