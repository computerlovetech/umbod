<script lang="ts">
  import Button from '#lib/components/admin/shared/Button.svelte';
  import LoadingButton from '#lib/components/admin/shared/LoadingButton.svelte';
  import Select from '#lib/components/admin/shared/Select.svelte';
  import Checkbox from '#lib/components/shared/Checkbox.svelte';
  import ModalShell from '#lib/components/shared/ModalShell.svelte';
  import TextField from '#lib/components/shared/TextField.svelte';
  import type { PersonalTokenState } from './personal-token-state.svelte';

  let { state }: { state: PersonalTokenState } = $props();
  const id = $props.id();
</script>

<ModalShell title={state.issuedToken ? 'Access token created' : 'Create access token'} titleId={`${id}-title`} close={state.closeCreate} closeDisabled={state.creating} initialFocus={'input[name="token-name"]'} --modal-width="32rem" --modal-overflow="auto">
  {#if state.issuedToken}
    <div class="result">
      <p>Copy your token now. It won’t be shown again.</p>
      <textarea aria-label="Access token" readonly value={state.issuedToken} rows="3" {@attach (element: HTMLTextAreaElement): void => element.focus()}></textarea>
      <div class="actions">
        <Button variant="secondary" onclick={state.closeCreate}>Done</Button>
        <LoadingButton loading={state.copyPending} label="Copy token" loadingLabel="Copying token" onclick={state.copy} />
      </div>
      {#if state.copySucceeded}<p role="status">Token copied.</p>{/if}
    </div>
  {:else}
    <form aria-label="Create access token" onsubmit={(event: SubmitEvent): void => { event.preventDefault(); void state.create(); }}>
      <fieldset disabled={state.creating} aria-label="Token details">
        <TextField id={`${id}-name`} name="token-name" label="Token name" required maxlength={256} value={state.tokenName} oninput={(event: Event): void => state.setTokenName((event.currentTarget as HTMLInputElement).value)} />
        <Select label="Expiration" options={state.expirationOptions} value={state.expiration} onchange={state.selectExpiration} disabled={state.creating} />
        <fieldset class="permissions">
          <legend>Permissions</legend>
          <Checkbox id={`${id}-agent-logs`} label="Send agent logs" checked={state.allowsAgentLogs} onchange={(event: Event): void => state.setAgentLogs((event.currentTarget as HTMLInputElement).checked)} />
        </fieldset>
      </fieldset>
      <div class="actions">
        <Button type="button" variant="secondary" data-dialog-cancel onclick={state.closeCreate} disabled={state.creating}>Cancel</Button>
        <LoadingButton type="submit" loading={state.creating} disabled={state.pending} label="Create token" loadingLabel="Creating token" />
      </div>
    </form>
  {/if}
  {#if state.error}<p class="admin-message admin-message--error" role="alert">{state.error}</p>{/if}
</ModalShell>

<style>
  p { color: var(--admin-muted); font-size: 14px; line-height: 1.6; margin: 0; }
  form, .result { display: grid; gap: 1rem; margin-top: 1.25rem; }
  fieldset { display: grid; gap: 1rem; border: 0; padding: 0; margin: 0; min-width: 0; }
  legend { color: var(--admin-ink); font-size: .875rem; font-weight: 600; padding: 0; margin-bottom: .375rem; }
  textarea { width: 100%; box-sizing: border-box; padding: .65rem; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-panel); color: var(--admin-ink); font-family: var(--admin-mono); font-size: 12px; line-height: 1.6; resize: vertical; }
  .actions { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: .75rem; }
</style>
