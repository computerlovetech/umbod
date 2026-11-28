<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import type { AgentTokenMetadata } from '#lib/admin/agent-tokens/domain/schemas.js';
  import type { AgentTokens } from '#lib/admin/agent-tokens/port.js';
  import type { CatalogueGroup } from '#lib/admin/groups/domain/schemas.js';
  import { adminApi } from '#lib/admin/infrastructure/admin-api.js';
  import AdminRecordList from '#lib/components/admin/shared/AdminRecordList.svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import DateTimeView from '#lib/components/shared/DateTimeView.svelte';
  import PlusIcon from '#lib/components/shared/PlusIcon.svelte';
  import SubpageContainer from '#lib/components/shared/workspace/SubpageContainer.svelte';
  import AgentTokenDialog from './AgentTokenDialog.svelte';
  import { AgentTokensState } from './agent-tokens-state.svelte.js';

  let { agents, groups, api = adminApi().agentTokens }: {
    agents: readonly AgentTokenMetadata[];
    groups: readonly CatalogueGroup[];
    api?: AgentTokens;
  } = $props();

  function createState(): AgentTokensState {
    return new AgentTokensState(api, agents, groups);
  }

  const state = createState();
  onMount(state.observeExpiry);
  onDestroy(state.dispose);
</script>

<SubpageContainer title="Agent tokens">
  {#snippet actions()}
    <Button disabled={state.pending || !state.groups.length} onclick={state.openCreate}><PlusIcon />Create agent token</Button>
  {/snippet}
  {#if !state.groups.length}<p>Create a <a href="/admin/groups">group</a> before issuing an agent token.</p>{/if}
  {#if state.error && state.dialog.kind === 'closed'}<p class="admin-message admin-message--error" role="alert">{state.error}</p>{/if}
  <AdminRecordList items={state.agents} keyOf={(agent) => agent.agent_id} label="Agent tokens" recordHeading="Agent" detailHeading="Expiration" emptyMessage="No agent tokens yet.">
    {#snippet identity(agent)}
      <h2>{agent.display_name}</h2>
      <div class="metadata">Group: {state.groupLabel(agent.group_id)}</div>
      <div class="metadata">Agent ID: <code>{agent.agent_id}</code></div>
    {/snippet}
    {#snippet detail(agent)}
      {@const status = state.statusOf(agent)}
      <div class="metadata">
        <span class={['status', { active: status === 'active' }]}>{status}</span>
        {#if agent.expires_at === null}<div>Never expires</div>{:else}<div>Expires <DateTimeView value={agent.expires_at} /></div>{/if}
      </div>
    {/snippet}
    {#snippet actions(agent)}
      <Button variant="secondary" iconOnly disabled={state.pending} aria-label={`Rotate token for ${agent.display_name}`} title="Rotate token" onclick={() => state.openRotate(agent)}>
        <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M20 4v5h-5M4 20v-5h5M5 9a7.5 7.5 0 0 1 12.6-3L20 9M4 15l2.4 3A7.5 7.5 0 0 0 19 15" /></svg>
      </Button>
      {#if agent.status !== 'revoked'}
        <Button variant="danger" iconOnly disabled={state.pending} aria-label={`Revoke token for ${agent.display_name}`} title="Revoke token" onclick={() => state.openRevoke(agent)}>
          <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"><circle cx="12" cy="12" r="8" /><path d="m6.5 6.5 11 11" /></svg>
        </Button>
      {/if}
    {/snippet}
  </AdminRecordList>
  {#if state.dialog.kind !== 'closed'}<AgentTokenDialog {state} />{/if}
</SubpageContainer>

<style>
  h2 { font-size: 15px; margin: 0 0 4px; }
  .metadata, p { color: var(--admin-muted); font-size: 13px; }
  .status { display: inline-block; background: var(--admin-soft); border-radius: 999px; padding: .15rem .5rem; margin-bottom: .25rem; font-size: .75rem; font-weight: 650; text-transform: capitalize; }
  .status.active { background: var(--admin-accent-soft); color: var(--admin-accent); }
</style>
