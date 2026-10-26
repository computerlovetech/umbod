<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { adminApi } from '$lib/admin/infrastructure/admin-api';
  import type { PersonalServerAdministration } from '$lib/admin/personal-mcp-servers/administration';
  import type { InstanceConfigurationRoute } from '$lib/admin/instance-configuration-api';
  import PersonalServerDialog from './PersonalServerDialog.svelte';
  import PolicyFields from './PolicyFields.svelte';
  import Button from '../shared/Button.svelte';
  import { captureInvalidSubmission } from './form-validation';
  import { PersonalServerFormState } from './personal-server-form-state.svelte';
  let { connectorId, api, configuration, accessLost = () => {}, lockChanged = () => {}, externalLocked = false }: { connectorId: string; api?: PersonalServerAdministration; configuration?: InstanceConfigurationRoute; accessLost?: () => void; lockChanged?: (locked: boolean) => void; externalLocked?: boolean } = $props();
  const dependencies = untrack(() => {
    const composite = api && configuration ? null : adminApi();
    return { api: api ?? composite!.personalServers, configuration: configuration ?? composite!.instanceConfiguration };
  });
  const state = new PersonalServerFormState(dependencies.api, dependencies.configuration, untrack(() => connectorId), undefined, untrack(() => accessLost), untrack(() => lockChanged));
  onMount(() => { void state.reload(); return state.dispose; });
</script>
<section aria-label="Personal OAuth settings">
  <p>Current Group permissions trust all tools available to each downstream user, including future tools after explicit rediscovery. No per-tool approval, activation or tool grants are required. Publication does not provide OAuth authorization, user enablement or private discovery.</p>
  <a href="/admin/group-permissions/connectors">Group permissions</a>
  <p>Each user manages their own enablement, OAuth sign-in and private tool discovery in <a href="/dashboard">Dashboard</a>. These administrator settings do not show a user's authorization or private inventory.</p>
  <p>Server details and endpoint are read-only after registration. The registration path is an identifier, not a shared proxy connection.</p>
  {#if state.message}<p role="alert">{state.message}</p>{/if}
  <Button variant="secondary" disabled={externalLocked || state.busy || state.loading || state.authenticationLost} onclick={state.reload}>Reload OAuth settings</Button>
  {#if state.loading}<p role="status">Loading OAuth settings…</p>{/if}
  {#if state.policy}
    <h3>OAuth provider policy</h3>
    <p>Revision: <code>{state.policy.revision}</code></p>
    <form {@attach captureInvalidSubmission(state.handleNativeInvalid)} onsubmit={(event) => { event.preventDefault(); state.requestConfirmation('policy'); }}>
      <fieldset disabled={externalLocked || state.locked || state.confirmation !== null}>
        <PolicyFields form={state.form} idPrefix={`personal-policy-${connectorId}`} />
        <Button type="submit">Review changes</Button>
      </fieldset>
    </form>
  {/if}
</section>
{#if state.confirmation}
  <PersonalServerDialog title="Save OAuth settings?" titleId="personal-confirm-title" descriptionId="personal-confirm-description" close={state.close}>
    <p id="personal-confirm-description">An effective change erases ALL users' saved authorizations and pending sign-ins for this server. User enablement, publication and group grants persist. Remote tokens are not revoked. Every confidential save explicitly rotates the client secret.</p>
    <Button variant="secondary" onclick={state.close}>Cancel</Button>
    <Button variant="danger" disabled={externalLocked || state.locked} onclick={state.confirm}>Save settings</Button>
  </PersonalServerDialog>
{/if}
<style>
  section { min-width: 0; }
  p { color: var(--admin-muted); line-height: 1.6; }
  a { color: var(--admin-accent); }
  fieldset { border: 0; padding: 0; margin: 0; display: grid; gap: 18px; min-width: 0; }
</style>
