<script lang="ts">
  import { onDestroy, untrack } from 'svelte';
  import PersonalServerDialog from './PersonalServerDialog.svelte';
  import AdminConfigurationField from '../shared/AdminConfigurationField.svelte';
  import Button from '../shared/Button.svelte';
  import Select from '../shared/Select.svelte';
  import PolicyFields from './PolicyFields.svelte';
  import PersonalServerDiscoveryFields from './PersonalServerDiscoveryFields.svelte';
  import { captureInvalidSubmission } from './form-validation';
  import type { PersonalServerFormState } from './personal-server-form-state.svelte';
  import type { PolicyProposal } from './policy-form.svelte';
  let { state, close, reload, proposal }: { state: PersonalServerFormState; close: () => void; reload: () => void; proposal?: PolicyProposal } = $props();
  onDestroy(untrack(() => state.form.clearSecret));
</script>
  <PersonalServerDialog title={state.editing ? "Edit MCP server with personal authorization" : "Register MCP server with personal authorization"} titleId="personal-create-title" {close}>
    <div class="modal-content">
      {#if !state.editing}<p class="setup-step">Step 4 of 4 · Configure</p>{/if}
      {#if state.message}<p role="alert">{state.message}</p>{/if}
      {#if state.blocked}<Button variant="secondary" disabled={state.busy || state.loading} onclick={reload}>{state.editing ? "Reload OAuth settings" : "Reload servers"}</Button>{/if}
      {#if state.loading}<p role="status">Loading OAuth settings…</p>{/if}
      {#if state.confirmation}
        <section aria-labelledby="personal-confirm-title">
          <h3 id="personal-confirm-title" tabindex="-1" {@attach (element: HTMLHeadingElement): void => element.focus()}>Save OAuth settings?</h3>
          <p>Changed settings disconnect all users, cancel pending sign-ins and unpublish the server. Remote tokens are not revoked. Confidential saves rotate the secret.</p>
          <div class="actions"><Button variant="secondary" onclick={state.close}>Back</Button><Button variant="danger" disabled={!state.readyForPolicyReview} onclick={state.confirm}>Save settings</Button></div>
        </section>
      {:else}
      <form {@attach captureInvalidSubmission(state.handleNativeInvalid)} onsubmit={(event) => { event.preventDefault(); if (state.editing) state.requestConfirmation('policy'); else void state.create(); }}>
        <fieldset disabled={state.editing ? state.locked || !state.policy : !state.canRegister}>
          <div class="section-heading">
            <h3>Server details</h3>
          </div>
          <AdminConfigurationField readonly={state.editing} id="personal-endpoint" name="endpoint" label="HTTPS MCP endpoint" type="url" placeholder="https://mcp.example.com/mcp" onblur={state.editing ? undefined : state.discovery.blur} required value={state.metadata.endpoint} oninput={(event) => state.setMetadata('endpoint', (event.currentTarget as HTMLInputElement).value)} />
          <AdminConfigurationField readonly={state.editing} id="personal-name" name="name" label="Server name" placeholder="Acme MCP" required value={state.metadata.name} oninput={(event) => state.setMetadata('name', (event.currentTarget as HTMLInputElement).value)} />
          <AdminConfigurationField readonly={state.editing} id="personal-prefix" name="prefix" label="Tool name prefix" placeholder="Acme_MCP" pattern="[a-zA-Z0-9_\-]+" required value={state.metadata.prefix} oninput={(event) => state.setMetadata('prefix', (event.currentTarget as HTMLInputElement).value)} />
          <AdminConfigurationField readonly={state.editing} id="personal-description" name="description" label="Capability description" placeholder="Search projects and manage tasks in Acme." maxlength={300} required value={state.metadata.description} oninput={(event) => state.setMetadata('description', (event.currentTarget as HTMLInputElement).value)} />
          <AdminConfigurationField readonly={state.editing} id="personal-path" name="path" label="Registration path identifier" inputPrefix="/mcp/proxies/" placeholder="acme-mcp" pattern="[a-z0-9][a-z0-9\-]&#123;0,62&#125;" maxlength={63} required value={state.metadata.path} oninput={(event) => state.setMetadata('path', (event.currentTarget as HTMLInputElement).value)} />
          <div class="section-heading">
            <h3>OAuth application</h3>
          </div>
          {#if state.editing}
            <PolicyFields form={state.form} {proposal} idPrefix="personal-edit" onClientSelection={state.selectClient} />
            {#if state.form.automatic}
              {#if state.discovery.pending}<p role="status">Discovering automatic application settings…</p>
              {:else if state.discovery.failed}
                <p role="alert">{state.discovery.failureMessage}</p>
                <Button variant="secondary" onclick={state.discovery.retry}>Retry discovery</Button>
              {:else if state.discovery.issuers.length && !state.discovery.result}
                <Select id="personal-edit-discovery-issuer" label="OAuth issuer" options={state.discovery.issuerOptions} value={state.discovery.selectedIssuer} onchange={state.discovery.selectIssuer} />
              {:else if state.discovery.automaticRegistrationUnavailable}
                <p role="status">Automatic setup is unsupported. Choose an existing client option instead.</p>
                <Button variant="secondary" onclick={state.discovery.retry}>Retry discovery</Button>
              {:else if state.automaticEditIssuer}
                <p>Automatic registration issuer: <code>{state.automaticEditIssuer}</code></p>
              {/if}
            {/if}
          {:else}
            <PersonalServerDiscoveryFields state={state.discovery} form={state.form}>
              {#snippet clientSetup()}
                <PolicyFields form={state.form} idPrefix="personal-registration" discoveredIssuer={state.discovery.result?.issuer_url}>
                  {#snippet scopes()}{/snippet}
                </PolicyFields>
              {/snippet}
            </PersonalServerDiscoveryFields>
          {/if}
          {#if !state.editing && state.creationBlocker}<p id="personal-creation-blocker" class="creation-blocker" role="status">{state.creationBlocker}</p>{/if}
          <div class="actions"><Button variant="secondary" onclick={close}>Cancel</Button><Button type="submit" aria-describedby={!state.editing && state.creationBlocker ? 'personal-creation-blocker' : undefined} disabled={state.editing ? !state.readyForPolicyReview : !state.canSaveCreation}>{state.editing ? "Review changes" : "Register unpublished server"}</Button></div>
        </fieldset>
      </form>
      {/if}
    </div>
  </PersonalServerDialog>
<style>
  .modal-content { overflow-y: auto; min-height: 0; padding-top: 8px; }
  fieldset { border: 0; padding: 0; margin: 0; display: grid; gap: 18px; min-width: 0; }
  .setup-step { margin: 0 0 1rem; color: var(--admin-muted); font-size: 13px; }
  .creation-blocker { margin: 0; color: var(--admin-muted); font-size: 13px; }
  .actions { display: flex; gap: 12px; flex-wrap: wrap; }
  .section-heading { display: grid; gap: 7px; }
  .section-heading h3 { color: var(--admin-ink); font-size: 1rem; margin: 0; }
</style>
