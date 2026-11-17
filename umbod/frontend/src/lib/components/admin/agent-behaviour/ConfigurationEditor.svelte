<script lang="ts">
  import Button from '#lib/components/admin/shared/Button.svelte';
  import AdminToggle from '#lib/components/admin/shared/AdminToggle.svelte';
  import Select from '#lib/components/admin/shared/Select.svelte';
  import TextField from '#lib/components/shared/TextField.svelte';
  import TextAreaField from '#lib/components/shared/TextAreaField.svelte';
  import ModalShell from '#lib/components/shared/ModalShell.svelte';
  import type { ConfigurationState } from '#lib/agent-behaviour/state/configuration-state.svelte.js';
  let { state }: { state: ConfigurationState } = $props();
</script>

{#if state.message}<p role="status">{state.message}</p>{/if}
{#if !state.loaded}
  <Button disabled={state.busy} onclick={state.load}>{state.busy ? 'Loading…' : 'Retry patterns'}</Button>
{:else}
  <p class="reporting-mode">Reporting · {state.reportingMode}</p>
  <div class="cards">
    {#each state.patterns as pattern (pattern.id)}
      <article class="editor-card">
        <h2>{pattern.name || 'New pattern'}</h2>
        <p>{pattern.description}</p>
        <div class="actions">
          <AdminToggle checked={pattern.enabled} ariaLabel={`Enable ${pattern.name || 'new pattern'}`} disabled={state.busy} onchange={(): void => void state.updatePattern(pattern.id, 'enabled', !pattern.enabled)} />
          <span>{pattern.enabled ? 'Enabled' : 'Disabled'}</span>
          <Button variant="secondary" aria-label={`Edit ${pattern.name || 'new pattern'}`} disabled={state.busy} onclick={(): void => state.editPattern(pattern.id)}>Edit</Button>
          <Button variant="quiet" aria-label={`Remove ${pattern.name || 'new pattern'}`} disabled={state.busy} onclick={(): void => state.removePattern(pattern.id)}>Remove</Button>
        </div>
      </article>
    {:else}<p>No patterns configured.</p>{/each}
  </div>
  {#if state.selected}
    {@const pattern = state.selected}
    <ModalShell title={pattern.name ? 'Edit pattern' : 'New pattern'} titleId="pattern-editor-title" close={state.closeEditor} closeDisabled={state.busy} initialFocus="input" --modal-overflow="auto">
    <section aria-label="Pattern editor">
      <fieldset disabled={state.busy}>
        <TextField id="pattern-name" label="Name" value={pattern.name} maxlength={120} oninput={(event): void => void state.updatePattern(pattern.id, 'name', event.currentTarget.value)} />
        <TextAreaField id="pattern-description" label="What should the agent notice?" value={pattern.description} maxlength={2000} oninput={(event): void => void state.updatePattern(pattern.id, 'description', event.currentTarget.value)} />
        <TextAreaField id="pattern-inclusion" label="When it counts" value={pattern.inclusion_criteria} maxlength={4000} oninput={(event): void => void state.updatePattern(pattern.id, 'inclusion_criteria', event.currentTarget.value)} />
        <TextAreaField id="pattern-exclusion" label="When it does not count" value={pattern.exclusion_criteria} maxlength={4000} oninput={(event): void => void state.updatePattern(pattern.id, 'exclusion_criteria', event.currentTarget.value)} />
        <details>
          <summary>Advanced assessment settings</summary>
          <TextAreaField id="pattern-assessment" label="Assessment prompt override" value={pattern.assessment_prompt} maxlength={4000} oninput={(event): void => void state.updatePattern(pattern.id, 'assessment_prompt', event.currentTarget.value || pattern.description)} />
          <TextField id="pattern-categories" label="Categories (comma-separated)" value={pattern.categories.join(', ')} onchange={(event): void => void state.updatePattern(pattern.id, 'categories', event.currentTarget.value.split(',').map((value): string => value.trim()).filter(Boolean))} />
          <Select label="Polarity" value={pattern.polarity} options={[{ value: 'neutral', label: 'Neutral' }, { value: 'positive', label: 'Positive' }, { value: 'negative', label: 'Negative' }]} onchange={(value: string): void => state.updatePattern(pattern.id, 'polarity', value as 'positive' | 'negative' | 'neutral')} />
        </details>
      </fieldset>
      <Button disabled={state.busy} onclick={state.closeEditor}>Done editing</Button>
    </section>
    </ModalShell>
  {/if}
  <details class="editor-card">
    <summary>Reporting settings</summary>
    {#each state.settings as setting (setting.id)}
      <fieldset disabled={state.busy}>
        <legend>{setting.name}</legend>
        <TextAreaField id={`collection-instructions-${setting.id}`} label="Collection instructions" value={setting.collection_instructions} maxlength={8000} oninput={(event): void => state.updateSettings(setting.id, 'collection_instructions', event.currentTarget.value)} />
        <div class="actions"><AdminToggle checked={setting.enabled} ariaLabel={`Enable reporting for ${setting.name}`} disabled={state.busy} onchange={(): void => state.updateSettings(setting.id, 'enabled', !setting.enabled)} /><span>Reporting enabled</span></div>
        <div class="actions"><AdminToggle checked={setting.allow_proactive} ariaLabel="Allow agents to report without being asked" disabled={state.busy} onchange={(): void => state.updateSettings(setting.id, 'allow_proactive', !setting.allow_proactive)} /><span>Allow agents to report without being asked</span></div>
      </fieldset>
    {:else}<p>No reporting settings configured.</p>{/each}
  </details>
  <div class="actions">
    <span role="status">{state.dirty ? 'Unsaved changes' : 'All changes saved'}</span>
    <Button disabled={state.busy || !state.dirty || state.conflict} onclick={state.save}>{state.busy ? 'Saving…' : 'Save changes'}</Button>
    <Button variant="secondary" disabled={state.busy || (!state.dirty && !state.conflict)} onclick={state.discard}>Discard changes</Button>
  </div>
{/if}

<style>
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 20rem), 1fr)); gap: 1rem; margin: 1rem 0; }
  .editor-card { background: var(--admin-panel); padding: 1rem; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); margin: 1rem 0; overflow-wrap: anywhere; }
  .cards .editor-card { margin: 0; }
  fieldset { display: grid; gap: 1rem; border: 0; padding: 1rem 6px; min-width: 0; }
  h2 { margin: 0; font-size: 1.15rem; }
  .actions { display: flex; align-items: center; gap: .75rem; flex-wrap: wrap; }
  summary { cursor: pointer; font-weight: 600; }
  fieldset > details[open] { display: grid; gap: 1rem; }
</style>
