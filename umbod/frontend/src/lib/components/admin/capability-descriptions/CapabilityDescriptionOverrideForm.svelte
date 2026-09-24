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

<style>.override{border-top:1px solid #e9e9e7;display:grid;gap:.5rem;margin-top:1.5rem;padding-top:1rem}.override h3{margin:0}.override textarea{border:1px solid #d9d9d6;border-radius:6px;font:inherit;min-height:4rem;padding:.6rem;resize:vertical}.override textarea:read-only{background:#f7f7f5;color:#5f5e5b}.meta,.actions{display:flex;gap:.75rem;justify-content:space-between}.error{color:#9f2d20}.actions{justify-content:flex-start}</style>
