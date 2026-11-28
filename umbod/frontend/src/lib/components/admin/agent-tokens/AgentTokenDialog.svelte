<script lang="ts">
  import CopyableValue from '#lib/components/admin/connectors/CopyableValue.svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import Form from '#lib/components/admin/shared/Form.svelte';
  import LoadingButton from '#lib/components/admin/shared/LoadingButton.svelte';
  import Select from '#lib/components/admin/shared/Select.svelte';
  import ModalShell from '#lib/components/shared/ModalShell.svelte';
  import TextField from '#lib/components/shared/TextField.svelte';
  import type { AgentTokensState } from './agent-tokens-state.svelte.js';

  let { state }: { state: AgentTokensState } = $props();
  const id = $props.id();
  const dialog = $derived(state.dialog);
  const title = $derived(dialog.kind === 'issued' ? dialog.title : dialog.kind === 'rotate' ? 'Rotate agent token' : dialog.kind === 'revoke' ? 'Revoke agent token?' : 'Create agent token');

  function submit(event: SubmitEvent): void {
    event.preventDefault();
    if (event.currentTarget instanceof HTMLFormElement) void state.save(new FormData(event.currentTarget));
  }
</script>

<ModalShell {title} titleId={`${id}-title`} close={state.close} closeDisabled={state.pending} --modal-overflow="auto">
  {#if dialog.kind === 'issued'}
    <div class="result">
      <p>Copy this token now. It won’t be shown again.</p>
      <CopyableValue value={dialog.token} inlineLabel="agent token" />
      <div class="actions"><Button variant="secondary" onclick={state.close} {@attach (button: HTMLButtonElement): void => button.focus()}>Done</Button></div>
    </div>
  {:else if dialog.kind === 'revoke'}
    <div class="result">
      <p>Revoke the token for <strong>{dialog.agent.display_name}</strong>? It will stop working on the next request.</p>
      <p>Agent ID: <code>{dialog.agent.agent_id}</code></p>
      <div class="actions">
        <Button variant="secondary" data-dialog-cancel disabled={state.pending} onclick={state.close}>Cancel</Button>
        <LoadingButton variant="danger" label="Revoke token" loadingLabel="Revoking…" loading={state.pending} onclick={state.revoke} />
      </div>
    </div>
  {:else}
    {#snippet fields()}
      <fieldset disabled={state.pending}>
        {#if dialog.kind === 'create'}
          <TextField id={`${id}-name`} name="display_name" label="Agent name" value="" required />
          <Select label="Group" options={state.groupOptions} value={state.selectedGroup} onchange={state.selectGroup} disabled={state.pending} />
        {:else if dialog.kind === 'rotate'}
          <p>Issue a new token for <strong>{dialog.agent.display_name}</strong>. Any current token will stop working on the next request.</p>
          <p>Agent ID: <code>{dialog.agent.agent_id}</code></p>
        {/if}
        <Select label="Expiration" options={state.expirationOptions} value={state.expiration} onchange={state.selectExpiration} disabled={state.pending} />
      </fieldset>
      {#if state.error}<p class="admin-message admin-message--error" role="alert">{state.error}</p>{/if}
    {/snippet}
    {#snippet actions()}
      <Button variant="secondary" data-dialog-cancel disabled={state.pending} onclick={state.close}>Cancel</Button>
      <LoadingButton type="submit" label={dialog.kind === 'rotate' ? 'Rotate token' : 'Create token'} loadingLabel="Saving…" loading={state.pending} />
    {/snippet}
    <Form onsubmit={submit} {fields} {actions} />
  {/if}
</ModalShell>

<style>
  p { color: var(--admin-muted); font-size: 14px; line-height: 1.55; margin: 0; }
  .result { display: grid; gap: 1rem; margin-top: 1.25rem; }
  fieldset { display: grid; gap: 1rem; border: 0; padding: 0; margin: 0; min-width: 0; }
  .actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: .75rem; }
</style>
