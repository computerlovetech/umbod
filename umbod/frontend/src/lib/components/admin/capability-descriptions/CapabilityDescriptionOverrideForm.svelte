<script lang="ts">
  import { onMount } from 'svelte';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import { CapabilityDescriptionsBrowserRoute } from '$lib/admin/capability-descriptions-browser-api';
  import type { ConnectorKind } from '$lib/admin/capability-descriptions';
  import { useToast } from '$lib/components/feedback';
  import { CapabilityDescriptionOverrideState } from './capability-description-override-state.svelte';

  let { kind, connectorId }: { kind: ConnectorKind; connectorId: string } = $props();
  const api = new CapabilityDescriptionsBrowserRoute();
  const state = new CapabilityDescriptionOverrideState(undefined, useToast());
  onMount(() => { void state.load(() => api.get(kind, connectorId)); });
  const save = (): void => { if (state.current) void state.save(() => api.set(kind, connectorId, state.draft, state.current!.override.revision)); };
  const restore = (): void => { if (state.current) void state.restore(() => api.clear(kind, connectorId, state.current!.override.revision)); };
</script>

<section class="override" aria-labelledby={`capability-override-${connectorId}`}>
  <h3 id={`capability-override-${connectorId}`}>Capability description</h3>
  {#if state.loading}<p role="status">Loading capability description…</p>
  {:else if state.current}
    <label for={`base-description-${connectorId}`}>Default description</label>
    <textarea id={`base-description-${connectorId}`} readonly value={state.current.base_description}></textarea>
    <label for={`effective-description-${connectorId}`}>Effective preview</label>
    <textarea id={`effective-description-${connectorId}`} readonly value={state.current.override.state === 'overridden' ? state.draft : state.current.base_description}></textarea>
    <label for={`override-description-${connectorId}`}>Custom agent-facing description</label>
    <textarea id={`override-description-${connectorId}`} value={state.draft} oninput={(event) => state.updateDraft(event.currentTarget.value)} aria-describedby={`override-count-${connectorId} override-validation-${connectorId}`} aria-invalid={Boolean(state.validationMessage)} maxlength="301"></textarea>
    <div class="meta"><span id={`override-count-${connectorId}`}>{state.characterCount}/300</span>{#if state.validationMessage}<span id={`override-validation-${connectorId}`} class="error">{state.validationMessage}</span>{/if}</div>
    <div class="actions"><Button disabled={!state.canSave} onclick={save}>{state.saving ? 'Saving…' : 'Save custom description'}</Button>{#if state.current.override.state === 'overridden'}<Button variant="secondary" disabled={state.saving} onclick={state.requestRestore}>Use default description</Button>{/if}</div>
    {#if state.confirmingRestore}<div role="alertdialog" aria-modal="true" aria-label="Use default description confirmation"><p>Remove the custom description and use the default description?</p><Button variant="secondary" onclick={state.cancelRestore}>Cancel</Button><Button variant="danger" onclick={restore}>Confirm restore</Button></div>{/if}
  {/if}
  {#if state.message}<p role="status">{state.message}</p>{/if}
</section>

<style>
  .override { color: var(--admin-ink); display: grid; gap: .75rem; margin-top: 1.25rem; min-height: 0; overflow-y: auto; padding: .25rem; }
  .override h3 { font-size: 1rem; margin: 0 0 .25rem; }
  .override label { font-size: 13px; font-weight: 600; }
  .override textarea { background: var(--admin-panel); border: 1px solid var(--admin-border-strong); border-radius: var(--admin-radius); box-sizing: border-box; color: var(--admin-ink); font: inherit; font-size: 14px; line-height: 1.55; min-height: 5rem; min-width: 0; padding: .7rem; resize: vertical; width: 100%; }
  .override textarea:read-only { background: var(--admin-soft); color: var(--admin-muted); }
  .override textarea:focus-visible { border-color: var(--admin-accent); outline: 2px solid var(--admin-focus); outline-offset: 1px; }
  .override textarea[aria-invalid='true'] { border-color: var(--admin-danger); }
  .meta, .actions { display: flex; flex-wrap: wrap; gap: .75rem; justify-content: space-between; }
  .meta { color: var(--admin-muted); font-size: 12px; line-height: 1.5; }
  .error { color: var(--admin-danger-text); }
  .actions { border-top: 1px solid var(--admin-border); justify-content: flex-start; padding-top: 1rem; }
  .override [role='status'] { color: var(--admin-muted); font-size: 14px; line-height: 1.55; margin: 0; }
  .override [role='alertdialog'] { background: var(--admin-warning-bg); border: 1px solid var(--admin-warning-border); border-radius: var(--admin-radius); color: var(--admin-warning-text); display: flex; flex-wrap: wrap; gap: .75rem; padding: 1rem; }
  .override [role='alertdialog'] p { flex-basis: 100%; font-size: 14px; line-height: 1.55; margin: 0; }
</style>
