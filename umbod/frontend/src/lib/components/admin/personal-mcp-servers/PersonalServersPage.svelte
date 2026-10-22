<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { adminApi } from '$lib/admin/infrastructure/admin-api';
  import type { PersonalServerAdministration } from '$lib/admin/personal-mcp-servers/administration';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
  import AdminShell from '../AdminShell.svelte';
  import PersonalServerDialog from './PersonalServerDialog.svelte';
  import { captureInvalidSubmission } from './form-validation';
  import AdminConfigurationField from '../shared/AdminConfigurationField.svelte';
  import Button from '../shared/Button.svelte';
  import PolicyFields from './PolicyFields.svelte';
  import { PersonalServersState } from './personal-servers-state.svelte';

  let { accountIdentity, api, requestedId = null, selectionChanged = () => {} }: {
    accountIdentity: HeaderAccountIdentityState;
    api?: PersonalServerAdministration;
    requestedId?: string | null;
    selectionChanged?: (id: string | null) => void;
  } = $props();
  const state = new PersonalServersState(untrack(() => api ?? adminApi().personalServers), untrack(() => selectionChanged));
  onMount(() => {
    void state.reload(untrack(() => requestedId));
    return state.dispose;
  });
  const confirmations = {
    policy: { title: 'Save OAuth settings?', label: 'Save settings', description: "An effective change erases ALL users' saved authorizations and pending sign-ins for this server. User enablement, publication and group grants persist. Remote tokens are not revoked. Every confidential save explicitly rotates the client secret." },
    publish: { title: 'Publish personal MCP server?', label: 'Publish', description: 'Publication allows selection only by explicitly permitted groups. Approved tool contracts, activation and tool permissions remain separate prerequisites for execution. Publication does not authorize users or discover tools.' },
    withdraw: { title: 'Withdraw personal MCP server?', label: 'Withdraw', description: 'After the user catalogue reloads, this server is no longer eligible for new selection. Withdrawal does not revoke remote tokens or disconnect existing owners.' },
    delete: { title: 'Delete personal MCP server?', label: 'Delete server', description: 'This permanently removes the server and its saved local authorizations and policy. Remove connector and tool grants first. Remote tokens are not revoked.' }
  };
</script>

<svelte:head><title>Personal MCP servers</title></svelte:head>
<AdminShell activeItem="personalMcpServers" {accountIdentity} contentWidth="wide">
  <h1 id="personal-servers-heading" tabindex="-1">Personal MCP servers</h1>
  <p>The global allowlist of administrator-registered personal servers. Users connect with their own accounts; registration is not universal access.</p>
  <aside class="guidance" aria-label="Publication and execution guidance">
    Publication allows selection by explicitly permitted groups. Approved tool contracts (API-only in this interface), activation and tool permissions are separate prerequisites before execution.
    <a href="/admin/group-permissions">Group permissions</a>
  </aside>
  <div class="actions">
    <Button disabled={state.locked} onclick={state.openCreate}>Register personal server</Button>
    <Button variant="secondary" disabled={state.busy || state.loading} onclick={() => state.reload()}>Reload servers</Button>
    <a href="/admin/downstream-mcp-connectors">Shared MCP proxy connectors</a>
  </div>
  {#if state.message}<p role="alert" class="message">{state.message}</p>{/if}
  {#if state.loading}<p role="status">Loading personal MCP servers…</p>{/if}
  <div class="workspace" aria-busy={state.busy || state.loading}>
    <nav aria-label="Personal server allowlist">
      {#each state.records as server (server.connector_id)}
        <button type="button" class={{ active: state.selectedId === server.connector_id }} disabled={state.busy || state.blocked || state.authenticationLost} onclick={() => state.select(server.connector_id)}>
          {server.display_name}<small>{server.publication_status === 'published' ? 'Published' : 'Registered · Unpublished'}</small>
        </button>
      {:else}
        {#if !state.loading && !state.authenticationLost}<p>No personal servers loaded.</p>{/if}
      {/each}
    </nav>
    {#if state.selected && state.policy && !state.creating}
      <section aria-label="Selected personal server">
        <h2>{state.selected.display_name}</h2>
        <p class="status">{state.selected.publication_status === 'published' ? 'Published' : 'Registered · Unpublished'}</p>
        <dl>
          <dt>Server ID</dt><dd>{state.selected.connector_id}</dd>
          <dt>Server name</dt><dd>{state.selected.display_name}</dd>
          <dt>Endpoint URL</dt><dd>{state.selected.endpoint_url}</dd>
          <dt>Tool name prefix</dt><dd>{state.selected.tool_name_prefix}</dd>
          <dt>Registration path</dt><dd>{state.selected.public_path}</dd>
          <dt>Description</dt><dd>{state.selected.capability_description}</dd>
        </dl>
        <p>Server details and endpoint cannot be changed after registration.</p>
        <div class="actions">
          {#if state.selected.publication_status === 'unpublished'}
            <Button disabled={state.locked} onclick={() => state.requestConfirmation('publish')}>Publish</Button>
          {:else}
            <Button variant="secondary" disabled={state.locked} onclick={() => state.requestConfirmation('withdraw')}>Withdraw publication</Button>
          {/if}
          <Button variant="danger" disabled={state.locked} onclick={() => state.requestConfirmation('delete')}>Delete server</Button>
        </div>
        <h3>OAuth provider policy</h3>
        <form {@attach captureInvalidSubmission(state.handleNativeInvalid)} onsubmit={(event) => { event.preventDefault(); state.requestConfirmation('policy'); }}>
          <fieldset disabled={state.locked || state.confirmation !== null}>
            <PolicyFields form={state.form} />
            <Button type="submit" disabled={state.locked}>Review changes</Button>
          </fieldset>
        </form>
      </section>
    {/if}
  </div>
</AdminShell>

{#if state.creating}
  <PersonalServerDialog title="Register personal MCP server" titleId="personal-create-title" descriptionId="personal-create-description" close={state.close}>
    <div class="modal-content">
      <p id="personal-create-description">Registration starts unpublished. No discovery, group grants, user enablement or consent is performed.</p>
      {#if state.message}<p role="alert">{state.message}</p>{/if}
      {#if state.blocked}<Button variant="secondary" disabled={state.busy || state.loading} onclick={() => state.reload()}>Reload servers</Button>{/if}
      <form {@attach captureInvalidSubmission(state.handleNativeInvalid)} onsubmit={(event) => { event.preventDefault(); void state.create(); }}>
        <fieldset disabled={state.locked}>
          <AdminConfigurationField id="personal-name" name="name" label="Server name" required value={state.metadata.name} oninput={(event) => state.setMetadata('name', (event.currentTarget as HTMLInputElement).value)} />
          <AdminConfigurationField id="personal-endpoint" name="endpoint" label="HTTPS MCP endpoint" required value={state.metadata.endpoint} oninput={(event) => state.setMetadata('endpoint', (event.currentTarget as HTMLInputElement).value)} />
          <AdminConfigurationField id="personal-prefix" name="prefix" label="Tool name prefix" required value={state.metadata.prefix} oninput={(event) => state.setMetadata('prefix', (event.currentTarget as HTMLInputElement).value)} />
          <AdminConfigurationField id="personal-description" name="description" label="Capability description" required value={state.metadata.description} oninput={(event) => state.setMetadata('description', (event.currentTarget as HTMLInputElement).value)} />
          <AdminConfigurationField id="personal-path" name="path" label="Registration path identifier" required value={state.metadata.path} helperText="A unique, fixed registration path identifier under /mcp/proxies/. This does not provide a shared proxy connection or authorize execution. Server details cannot be changed later." oninput={(event) => state.setMetadata('path', (event.currentTarget as HTMLInputElement).value)} />
          <PolicyFields form={state.form} />
          <div class="actions"><Button variant="secondary" onclick={state.close}>Cancel</Button><Button type="submit">Register unpublished server</Button></div>
        </fieldset>
      </form>
    </div>
  </PersonalServerDialog>
{/if}
{#if state.confirmation}
  <PersonalServerDialog title={confirmations[state.confirmation].title} titleId="personal-confirm-title" descriptionId="personal-confirm-description" close={state.close}>
    <div class="modal-content">
      <p id="personal-confirm-description">{confirmations[state.confirmation].description}</p>
      <div class="actions"><Button variant="secondary" onclick={state.close}>Cancel</Button><Button variant="danger" disabled={state.locked} onclick={() => state.confirm()}>{confirmations[state.confirmation].label}</Button></div>
    </div>
  </PersonalServerDialog>
{/if}

<style>
  h1 { letter-spacing: -0.04em; margin-top: 0; }
  p, aside { color: var(--admin-muted); line-height: 1.6; }
  a { color: var(--admin-accent); }
  .guidance { background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: 16px; }
  .guidance a { display: inline-block; margin-left: 8px; }
  .actions { align-items: center; display: flex; flex-wrap: wrap; gap: 12px; margin: 20px 0; }
  .workspace { display: grid; grid-template-columns: minmax(180px, 260px) minmax(0, 1fr); gap: 28px; margin-top: 28px; }
  nav { display: grid; align-content: start; gap: 8px; }
  nav button { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); color: var(--admin-ink); cursor: pointer; font: inherit; padding: 14px; text-align: left; overflow-wrap: anywhere; }
  nav button.active { border-color: var(--admin-accent); background: var(--admin-accent-soft); }
  small { display: block; color: var(--admin-muted); margin-top: 6px; }
  section { min-width: 0; }
  dl { display: grid; gap: 6px; }
  dt { color: var(--admin-muted); font-size: 13px; margin-top: 8px; }
  dd { color: var(--admin-ink); margin: 0; overflow-wrap: anywhere; }
  fieldset { border: 0; padding: 0; margin: 0; display: grid; gap: 18px; min-width: 0; }
  .message { border: 1px solid var(--admin-warning-border); padding: 12px; }
  .modal-content { overflow-y: auto; min-height: 0; padding-top: 8px; }
  @media (max-width: 720px) { .workspace { grid-template-columns: minmax(0, 1fr); } }
</style>
