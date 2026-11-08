<script lang="ts">
  import Button from '$lib/components/admin/shared/Button.svelte';
  import LoadingButton from '$lib/components/admin/shared/LoadingButton.svelte';
  import Select from '$lib/components/admin/shared/Select.svelte';
  import AdminConfigurationField from '$lib/components/admin/shared/AdminConfigurationField.svelte';
  import { nativeDialog } from '$lib/components/shared/dialogs/native-dialog';
  import type { TelemetrySetupState } from './telemetry-setup-state.svelte';

  let { state }: { state: TelemetrySetupState } = $props();
  const id = $props.id();
</script>

<dialog aria-labelledby={`${id}-title`} {@attach nativeDialog(state.closeCreate, () => !state.creating, 'input[name="token-name"]')}>
  <h2 id={`${id}-title`}>{state.configuration ? 'Token configuration' : 'Create telemetry token'}</h2>
  {#if state.configuration}
    <div class="configuration">
      <h3>{state.agent === 'codex' ? '~/.codex/config.toml' : '~/.claude/settings.json'}</h3>
      <p>This configuration contains a secret shown only once. Settings store it in plaintext: store them securely and do not commit them. Merge these entries while preserving existing settings. Logs can still include metadata and, with Codex, tool output.</p>
      <p><a href={state.agent === 'codex' ? 'https://developers.openai.com/codex/config-advanced#observability-and-telemetry' : 'https://code.claude.com/docs/en/monitoring-usage'} target="_blank" rel="noreferrer">Agent telemetry documentation</a></p>
      <textarea aria-label="Generated telemetry configuration" readonly value={state.configuration} rows="12" {@attach (element: HTMLTextAreaElement): void => element.focus()}></textarea>
      <div class="actions">
        <LoadingButton loading={state.copyPending} label="Copy configuration" loadingLabel="Copying configuration" onclick={state.copy} />
        <Button variant="secondary" onclick={state.closeCreate}>Done</Button>
      </div>
      {#if state.copySucceeded}<p role="status">Configuration copied.</p>{/if}
    </div>
  {:else}
    <form aria-label="Create telemetry token" onsubmit={(event: SubmitEvent): void => { event.preventDefault(); void state.create(); }}>
      <fieldset disabled={state.creating}>
        <Select label="Agent" options={state.agentOptions} value={state.agent} onchange={state.setAgent} disabled={state.creating} />
        <AdminConfigurationField id={`${id}-name`} name="token-name" label="Token name" required maxlength={256} value={state.tokenName} oninput={(event: Event): void => state.setTokenName((event.currentTarget as HTMLInputElement).value)} />
        <Select label="Expiration" options={state.expirationSelectOptions} value={String(state.expirationDays)} onchange={(value: string): void => state.setExpirationDays(Number(value))} disabled={state.creating} />
      </fieldset>
      <div class="actions">
        <Button type="button" variant="secondary" data-dialog-cancel onclick={state.closeCreate} disabled={state.creating}>Cancel</Button>
        <LoadingButton type="submit" loading={state.creating} disabled={state.pending} label="Create token" loadingLabel="Creating token" />
      </div>
    </form>
  {/if}
  {#if state.error}<p class="admin-message admin-message--error" role="alert">{state.error}</p>{/if}
</dialog>

<style>
  dialog { box-sizing: border-box; width: min(42rem, calc(100% - 2rem)); max-height: calc(100dvh - 2rem); overflow: auto; padding: 1.5rem; background: var(--admin-panel); color: var(--admin-ink); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); box-shadow: var(--admin-shadow-dialog); }
  dialog::backdrop { background: var(--admin-overlay); }
  h2 { font-size: 20px; letter-spacing: -0.025em; margin: 0; }
  h3 { font-size: 16px; margin: 0; overflow-wrap: anywhere; }
  p { color: var(--admin-muted); font-size: 14px; line-height: 1.6; }
  a { color: var(--admin-accent-strong); text-underline-offset: 3px; }
  form, .configuration { display: grid; gap: 1rem; margin-top: 1.25rem; }
  fieldset { display: grid; gap: 1rem; border: 0; padding: 0; margin: 0; min-width: 0; }
  textarea { width: 100%; box-sizing: border-box; padding: .65rem; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-panel); color: var(--admin-ink); font-family: var(--admin-mono); font-size: 12px; line-height: 1.6; resize: vertical; }
  .actions { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: .75rem; }
</style>
