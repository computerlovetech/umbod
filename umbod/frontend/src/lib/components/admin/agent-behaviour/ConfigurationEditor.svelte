<script lang="ts">
  import { tick } from 'svelte';
  import '#lib/styles/form-fields.css';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import AdminToggle from '#lib/components/admin/shared/AdminToggle.svelte';
  import ToolSaveBar from '#lib/components/admin/connectors/ToolSaveBar.svelte';
  import Select from '#lib/components/admin/shared/Select.svelte';
  import TextField from '#lib/components/shared/TextField.svelte';
  import TextAreaField from '#lib/components/shared/TextAreaField.svelte';
  import ModalShell from '#lib/components/shared/ModalShell.svelte';
  import { agentDiagnosticsHref } from '#lib/workspace/navigation.js';
  import type { ConfigurationState, ReportingPolicy } from '#lib/agent-behaviour/state/configuration-state.svelte.js';
  const reportingDescriptions: Record<ConfigurationState['reportingMode'], string> = {
    'When requested': 'Umbod accepts reports only when the user asks for them.',
    'Automatic reports allowed': 'Umbod also accepts proactive reports where allowed by the reporting settings, the user, and the client.',
    Off: 'Umbod does not accept new reports. Reporting requires at least one enabled reporting setting with an enabled pattern.'
  };

  const policies: readonly { id: ReportingPolicy; label: string; description: string }[] = [
    { id: 'requested', label: 'When requested', description: 'Accept reports only when the user asks for them.' },
    { id: 'proactive', label: 'Allow proactive reports', description: 'Also accept reports without a request if both the user and client allow it.' },
    { id: 'off', label: 'Off', description: 'Reject all new reports under this setting, even when requested.' }
  ];
  let { state, section = 'patterns' }: { state: ConfigurationState; section?: 'patterns' | 'reporting' } = $props();

  function categoryInput(form: HTMLFormElement | null): HTMLInputElement | null {
    const input = form?.elements.namedItem('category');
    return input instanceof HTMLInputElement ? input : null;
  }

  function addCategory(id: string, input: HTMLInputElement): boolean {
    const error = state.addCategory(id, input.value);
    input.setCustomValidity(error);
    if (error) {
      input.reportValidity();
      return false;
    }
    input.value = '';
    state.setPendingCategory('');
    input.focus();
    return true;
  }

  function savePatternEdit(id: string, button: HTMLButtonElement): void {
    if (!state.editorDirty) return;
    const input = categoryInput(button.form);
    if (input?.value.trim() && !addCategory(id, input)) return;
    state.closeEditor();
  }

  function removeCategory(id: string, category: string, button: HTMLButtonElement): void {
    const input = categoryInput(button.form);
    input?.setCustomValidity('');
    input?.focus();
    state.removeCategory(id, category);
  }

  async function deletePattern(id: string, button: HTMLButtonElement): Promise<void> {
    const row = button.closest('li');
    const neighbor = row?.nextElementSibling ?? row?.previousElementSibling;
    const nextFocus = neighbor?.querySelector<HTMLElement>('summary') ?? button.ownerDocument.getElementById('discard-diagnostics-changes');
    state.removePattern(id);
    await tick();
    if (!button.isConnected) nextFocus?.focus();
  }
</script>

{#snippet factIcon(path: string)}
  <svg class="fact-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d={path} /></svg>
{/snippet}

{#if state.message}<p role="status">{state.message}</p>{/if}
{#if !state.loaded}
  <Button disabled={state.busy} onclick={state.load}>{state.busy ? 'Loading…' : 'Retry patterns'}</Button>
{:else}
  <ToolSaveBar message={state.busy ? 'Working…' : state.dirty ? 'Unsaved changes' : ''} dirty={state.dirty} pending={state.busy}>
    <div class="actions save-actions">
      <Button id="discard-diagnostics-changes" variant="secondary" disabled={state.busy || (!state.dirty && !state.conflict)} onclick={state.discard}>Discard changes</Button>
      <Button disabled={state.busy || !state.dirty || state.conflict} onclick={state.save}>Save changes</Button>
    </div>
  </ToolSaveBar>
  <section hidden={section !== 'reporting'} aria-labelledby="reporting-settings-title">
    <header class="section-heading">
      <div>
        <h2 id="reporting-settings-title">Reporting settings</h2>
        <p>Choose which diagnostic reports to accept and what they should include. These settings do not hide the MCP reporting tool.</p>
      </div>
    </header>
    <div class="reporting-layout">
      <div class="editor-card reporting-form">
        {#each state.settings as setting (setting.id)}
          {#if state.settings.length > 1}<h3>{setting.name}</h3>{/if}
          <fieldset class="reporting-options" disabled={state.busy}>
            <legend>Which reports Umbod accepts{state.settings.length > 1 ? ` · ${setting.name}` : ''}</legend>
            {#each policies as policy (policy.id)}
              <label class="reporting-option">
                <input type="radio" name={`reporting-policy-${setting.id}`} checked={policy.id === (!setting.enabled ? 'off' : setting.allow_proactive ? 'proactive' : 'requested')} onchange={(): void => state.setReportingPolicy(setting.id, policy.id)} />
                <span><strong>{policy.label}</strong><small>{policy.description}</small></span>
              </label>
            {/each}
          </fieldset>
          <TextAreaField id={`collection-instructions-${setting.id}`} label={state.settings.length > 1 ? `Collection instructions · ${setting.name}` : 'Collection instructions'} value={setting.collection_instructions} disabled={state.busy} rows={6} maxlength={8000} oninput={(event): void => state.updateSettings(setting.id, 'collection_instructions', event.currentTarget.value)} />
        {:else}<p>No reporting settings configured.</p>{/each}
      </div>
      <aside class="editor-card reporting-summary" aria-labelledby="reporting-summary-title">
        <h3 id="reporting-summary-title">Reporting status</h3>
        <div role="status" aria-atomic="true">
          <p><strong>Saved mode: {state.savedReportingMode}</strong></p>
          <p>{reportingDescriptions[state.savedReportingMode]}</p>
          {#if !state.conflict && state.reportingMode !== state.savedReportingMode}
            <div class="reporting-draft">
              <p><strong>After saving: {state.reportingMode}</strong></p>
              <p>{reportingDescriptions[state.reportingMode]}</p>
            </div>
          {/if}
        </div>
        <div class="reporting-draft">
          <p>{state.enabledPatternCount} enabled {state.enabledPatternCount === 1 ? 'pattern' : 'patterns'}</p>
          <a class="admin-back-link" href={agentDiagnosticsHref}>Manage patterns <span aria-hidden="true">→</span></a>
        </div>
      </aside>
    </div>
  </section>
  <section hidden={section !== 'patterns'} aria-labelledby="diagnostic-patterns-title">
    <header class="section-heading">
      <div>
        <h2 id="diagnostic-patterns-title">Patterns</h2>
        <p>{state.enabledPatternCount} of {state.patterns.length} enabled</p>
      </div>
      <Button disabled={state.busy} onclick={state.addPattern}>Add pattern</Button>
    </header>
    {#if state.patterns.length}
      <ul class="pattern-list" role="list">
        {#each state.patterns as pattern (pattern.id)}
          {@const name = pattern.name || 'New pattern'}
          <li class="pattern-row">
            <details class="pattern-details">
              <summary class="pattern-summary"><span class="chevron" aria-hidden="true"></span><span>{name}</span></summary>
              <div class="pattern-inspection">
                <p>{pattern.description || 'No description'}</p>
                <dl class="pattern-facts">
                  <div class="rule-card inclusion-rule">
                    <dt>{@render factIcon('M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM8 12l2.5 2.5L16 9')} When it counts</dt>
                    <dd>{pattern.inclusion_criteria.trim() ? pattern.inclusion_criteria : 'Not specified'}</dd>
                  </div>
                  <div class="rule-card exclusion-rule">
                    <dt>{@render factIcon('M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM9 9l6 6m0-6-6 6')} When it does not count</dt>
                    <dd>{pattern.exclusion_criteria.trim() ? pattern.exclusion_criteria : 'Not specified'}</dd>
                  </div>
                </dl>
                <dl class="pattern-facts assessment-facts">
                  <div class="assessment-prompt">
                    <dt>{@render factIcon('M4 4h16v13H10l-6 4V4Zm4 5h8m-8 4h5')} Assessment prompt</dt>
                    <dd>{pattern.assessment_prompt || 'Not specified'}</dd>
                  </div>
                  <div>
                    <dt>{@render factIcon('M4 4h8l8 8-8 8-8-8V4Zm4 4h.01')} Categories</dt>
                    <dd class="fact-badges">
                      {#each pattern.categories as category, index (`${category}:${index}`)}
                        <span class="fact-badge">{category}</span>
                      {:else}None{/each}
                    </dd>
                  </div>
                  <div>
                    <dt>{@render factIcon('M3 12h18m-14-4-4 4 4 4m10-8 4 4-4 4')} Polarity</dt>
                    <dd><span class={['fact-badge', 'polarity', pattern.polarity]}>{pattern.polarity}</span></dd>
                  </div>
                </dl>
              </div>
            </details>
            <div class="pattern-actions">
              <AdminToggle checked={pattern.enabled} ariaLabel={`Enable ${name}`} disabled={state.busy} onchange={(): void => state.updatePattern(pattern.id, 'enabled', !pattern.enabled)} />
              <Button variant="quiet" iconOnly aria-label={`Edit ${name}`} title={`Edit ${name}`} disabled={state.busy} onclick={(): void => state.editPattern(pattern.id)}>
                <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="m15 4 5 5M4 20l5-1L21 7a2.1 2.1 0 0 0-5-5L4 14z" /></svg>
              </Button>
              <Button variant="danger" iconOnly aria-label={`Delete ${name}`} title={`Delete ${name}`} disabled={state.busy} onclick={(event): Promise<void> => deletePattern(pattern.id, event.currentTarget)}>
                <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M9 6V4h6v2M5 6l1 14h12l1-14M10 10v6M14 10v6" /></svg>
              </Button>
            </div>
          </li>
        {/each}
      </ul>
    {:else}<p>No patterns configured.</p>{/if}
  </section>
  {#if section === 'patterns' && state.selected}
    {@const pattern = state.selected}
    <ModalShell title={pattern.name ? 'Edit pattern' : 'New pattern'} titleId="pattern-editor-title" close={state.closeEditor} closeDisabled={state.busy} initialFocus="input" --modal-overflow="auto">
    <section aria-label="Pattern editor">
      <fieldset disabled={state.busy}>
        <TextField id="pattern-name" label="Name" value={pattern.name} maxlength={120} oninput={(event): void => void state.updatePattern(pattern.id, 'name', event.currentTarget.value)} />
        <TextAreaField id="pattern-description" label="What should the agent notice?" value={pattern.description} maxlength={2000} oninput={(event): void => void state.updatePattern(pattern.id, 'description', event.currentTarget.value)} />
        <TextAreaField id="pattern-inclusion" label="When it counts" value={pattern.inclusion_criteria} maxlength={4000} oninput={(event): void => void state.updatePattern(pattern.id, 'inclusion_criteria', event.currentTarget.value)} />
        <TextAreaField id="pattern-exclusion" label="When it does not count" value={pattern.exclusion_criteria} maxlength={4000} oninput={(event): void => void state.updatePattern(pattern.id, 'exclusion_criteria', event.currentTarget.value)} />
        <TextAreaField id="pattern-assessment" label="Assessment prompt override" value={pattern.assessment_prompt} maxlength={4000} oninput={(event): void => void state.updatePattern(pattern.id, 'assessment_prompt', event.currentTarget.value || pattern.description)} />
        <form id="pattern-category-form" class="form-field" onsubmit={(event): void => {
          event.preventDefault();
          const input = categoryInput(event.currentTarget);
          if (input) addCategory(pattern.id, input);
        }}>
          <label class="form-field-label" for="pattern-categories">Categories</label>
          {#if pattern.categories.length}
            <ul class="category-tags" role="list" aria-label="Added categories">
              {#each pattern.categories as category (category)}
                <li class="fact-badge category-tag">
                  <span>{category}</span>
                  <button type="button" class="remove-tag" aria-label={`Remove category ${category}`} onclick={(event): void => removeCategory(pattern.id, category, event.currentTarget)}>
                    {@render factIcon('M7 7l10 10M17 7 7 17')}
                  </button>
                </li>
              {/each}
            </ul>
          {/if}
          <div class="category-entry">
            <input id="pattern-categories" class="form-control" name="category" type="text" value={state.pendingCategory} placeholder="Add a category" autocomplete="off" required oninput={(event): void => {
              event.currentTarget.setCustomValidity('');
              state.setPendingCategory(event.currentTarget.value);
            }} />
            <Button type="submit" variant="secondary" aria-label="Add category">Add</Button>
          </div>
        </form>
        <Select label="Polarity" value={pattern.polarity} options={[{ value: 'neutral', label: 'Neutral' }, { value: 'positive', label: 'Positive' }, { value: 'negative', label: 'Negative' }]} onchange={(value: string): void => state.updatePattern(pattern.id, 'polarity', value as 'positive' | 'negative' | 'neutral')} />
      </fieldset>
      <div class="actions save-actions">
        <Button form="pattern-category-form" disabled={state.busy || !state.editorDirty} onclick={(event): void => savePatternEdit(pattern.id, event.currentTarget)}>Save</Button>
      </div>
    </section>
    </ModalShell>
  {/if}
{/if}

<style>
  .pattern-list { list-style: none; margin: .65rem 0 0; padding: 0; background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); overflow: clip; }
  .pattern-row { position: relative; }
  .pattern-row + .pattern-row { border-top: 1px solid var(--admin-border); }
  .pattern-summary { box-sizing: border-box; display: flex; align-items: center; gap: .75rem; min-height: 3.5rem; padding: .65rem 8.75rem .65rem .9rem; list-style: none; overflow-wrap: anywhere; }
  .pattern-summary::-webkit-details-marker { display: none; }
  .pattern-summary:focus-visible { outline-offset: -3px; }
  .pattern-summary:hover, .pattern-details[open] > .pattern-summary { background: var(--admin-soft); }
  .chevron { flex: none; width: .45rem; height: .45rem; margin-inline: .15rem; border-right: 2px solid currentColor; border-bottom: 2px solid currentColor; transform: rotate(-45deg); color: var(--admin-muted); }
  .pattern-details[open] > .pattern-summary .chevron { transform: rotate(45deg); }
  .pattern-actions { position: absolute; inset-block-start: .5625rem; inset-inline-end: .6rem; display: flex; align-items: center; gap: .25rem; }
  .pattern-inspection { padding: 1rem clamp(.9rem, 3vw, 1.75rem); border-top: 1px solid var(--admin-border); overflow-wrap: anywhere; }
  .pattern-inspection p { margin: 0; white-space: pre-wrap; }
  .pattern-facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 15rem), 1fr)); gap: .85rem 1.25rem; margin: .75rem 0 0; }
  .pattern-facts dt { display: flex; align-items: center; gap: .45rem; font-weight: 600; }
  .pattern-facts dd { color: var(--admin-muted); margin: .25rem 0 0; white-space: pre-wrap; }
  .fact-icon { flex: none; width: 1rem; height: 1rem; color: var(--fact-accent, var(--admin-muted)); }
  .rule-card { padding: .7rem .8rem; border: 1px solid; border-radius: var(--admin-radius); }
  .inclusion-rule { background: var(--admin-success-bg); border-color: var(--admin-success-border); --fact-accent: var(--admin-success-text); }
  .exclusion-rule { background: var(--admin-warning-bg); border-color: var(--admin-warning-border); --fact-accent: var(--admin-warning-text); }
  .assessment-facts { margin-top: 1rem; padding-top: .85rem; border-top: 1px solid var(--admin-border); align-items: start; }
  .assessment-prompt { padding: .6rem .75rem; background: var(--admin-soft); border-radius: var(--admin-radius); }
  .fact-badges { display: flex; flex-wrap: wrap; gap: .3rem; }
  .fact-badge { display: inline-block; max-width: 100%; padding: .1rem .5rem; border: 1px solid var(--admin-border); border-radius: 999px; color: var(--admin-ink); background: var(--admin-soft); font-size: .8rem; font-weight: 600; }
  .category-tags { display: flex; flex-wrap: wrap; gap: .35rem; list-style: none; margin: 0; padding: 0; }
  .category-tag { display: inline-flex; align-items: center; gap: .25rem; padding-inline-end: .2rem; overflow-wrap: anywhere; }
  .remove-tag { display: grid; place-items: center; flex: none; width: 1.5rem; height: 1.5rem; padding: 0; border: 0; border-radius: 50%; color: var(--admin-muted); background: transparent; cursor: pointer; }
  .remove-tag:hover { background: var(--admin-hover); color: var(--admin-ink); }
  .category-entry { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: .5rem; }
  .polarity { text-transform: capitalize; }
  .polarity.negative { background: var(--admin-danger-bg); border-color: var(--admin-danger-border); color: var(--admin-danger-text); }
  .polarity.positive { background: var(--admin-success-bg); border-color: var(--admin-success-border); color: var(--admin-success-text); }
  .editor-card { background: var(--admin-panel); padding: 1rem; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); margin: 1rem 0; overflow-wrap: anywhere; }
  fieldset { display: grid; gap: 1rem; border: 0; padding: 1rem 6px; min-width: 0; }
  h2 { margin: 0; font-size: 1.15rem; }
  .actions { display: flex; align-items: center; gap: .75rem; flex-wrap: wrap; }
  .save-actions { justify-content: flex-end; }
  .section-heading { display: flex; align-items: center; justify-content: space-between; gap: .75rem; flex-wrap: wrap; margin-bottom: .65rem; }
  .section-heading p, .reporting-summary p { margin: .35rem 0 0; font-size: .9rem; color: var(--admin-muted); }
  .reporting-summary strong { color: var(--admin-ink); }
  .reporting-layout { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(0, 1fr); gap: 1rem; align-items: start; }
  .reporting-layout .editor-card { margin: 0; }
  .reporting-form { display: grid; gap: .9rem; }
  .reporting-options { gap: .4rem; padding: 0; }
  .reporting-options legend { padding: 0; margin-bottom: .4rem; font-weight: 650; }
  .reporting-option { display: flex; align-items: start; gap: .5rem; padding: .55rem .65rem; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); }
  .reporting-option:has(:checked) { background: var(--admin-accent-soft); border-color: var(--admin-accent-border); }
  .reporting-option input { accent-color: var(--admin-accent); flex: none; margin: .24rem 0 0; }
  .reporting-option strong, .reporting-option small { display: block; }
  .reporting-option small { color: var(--admin-muted); }
  .reporting-summary { background: var(--admin-soft); }
  .reporting-summary a { gap: .3rem; margin-top: .35rem; }
  .reporting-draft { margin-top: .75rem; padding-top: .35rem; border-top: 1px solid var(--admin-border); }
  @media (max-width: 680px) { .reporting-layout { grid-template-columns: 1fr; } }
  summary { cursor: pointer; font-weight: 600; }
</style>
