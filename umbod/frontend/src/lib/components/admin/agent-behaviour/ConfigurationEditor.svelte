<script lang="ts">
  import { tick } from 'svelte';
  import '#lib/styles/form-fields.css';
  import AdminSettingsActions from '#lib/components/admin/shared/AdminSettingsActions.svelte';
  import AdminRecordList from '#lib/components/admin/shared/AdminRecordList.svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import PlusIcon from '#lib/components/shared/PlusIcon.svelte';
  import AdminToggle from '#lib/components/admin/shared/AdminToggle.svelte';
  import ToolSaveBar from '#lib/components/admin/connectors/ToolSaveBar.svelte';
  import Select from '#lib/components/admin/shared/Select.svelte';
  import TextField from '#lib/components/shared/TextField.svelte';
  import TextAreaField from '#lib/components/shared/TextAreaField.svelte';
  import Disclosure from '#lib/components/shared/Disclosure.svelte';
  import ModalShell from '#lib/components/shared/ModalShell.svelte';
  import type { ConfigurationState } from '#lib/agent-behaviour/state/configuration-state.svelte.js';
  import ReportingSettings from './ReportingSettings.svelte';
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

  async function savePatternEdit(id: string, button: HTMLButtonElement): Promise<void> {
    if (!state.editorDirty) return;
    const input = categoryInput(button.form);
    if (input?.value.trim() && !addCategory(id, input)) return;
    await state.savePatternEdit();
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
    const nextDisclosure = neighbor?.querySelector<HTMLButtonElement>('.pattern-details button[aria-expanded]');
    state.removePattern(id);
    await tick();
    if (!button.isConnected) (nextDisclosure ?? button.ownerDocument.getElementById('discard-diagnostics-changes'))?.focus();
  }
</script>

{#snippet factIcon(path: string)}
  <svg class="fact-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d={path} /></svg>
{/snippet}

{#snippet saveBar()}
  <ToolSaveBar message={state.busy ? 'Working…' : state.dirty ? 'Unsaved changes' : ''} dirty={state.dirty} pending={state.busy}>
    <div class="actions save-actions">
      <Button id="discard-diagnostics-changes" variant="secondary" disabled={state.busy || (!state.dirty && !state.conflict)} onclick={state.discard}>Discard changes</Button>
      <Button disabled={state.busy || !state.dirty || state.conflict} onclick={state.save}>Save changes</Button>
    </div>
  </ToolSaveBar>
{/snippet}

{#if state.message}<p role="status">{state.message}</p>{/if}
{#if !state.loaded}
  <Button disabled={state.busy} onclick={state.load}>{state.busy ? 'Loading…' : 'Retry loading diagnostics'}</Button>
{:else}
  {#if section === 'reporting'}
    <ReportingSettings {state} />
    <AdminSettingsActions busy={state.busy} dirty={state.dirty} conflict={state.conflict} onDiscard={state.discard} onSave={state.save} />
  {:else}
  {#if state.dirty || state.busy || state.conflict}
    {@render saveBar()}
  {/if}
  <section aria-labelledby="diagnostic-patterns-title">
    <header class="section-heading">
      <div>
        <h2 id="diagnostic-patterns-title">Patterns</h2>
        <p>{state.enabledPatternCount} of {state.patterns.length} enabled</p>
      </div>
      <Button disabled={state.busy} onclick={state.addPattern}><PlusIcon />Add pattern</Button>
    </header>
    <AdminRecordList items={state.patterns} keyOf={(pattern): string => pattern.id} label="Patterns" recordHeading="Pattern" detailHeading="Enabled" emptyMessage="No patterns configured.">
      {#snippet identity(pattern)}
        <div class="pattern-details">
          <Disclosure --disclosure-trigger-gap=".75rem">
            {#snippet label()}<span class="pattern-label">{pattern.name || 'New pattern'}</span>{/snippet}
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
          </Disclosure>
        </div>
      {/snippet}
      {#snippet detail(pattern)}
        <AdminToggle checked={pattern.enabled} ariaLabel={`Enable ${pattern.name || 'New pattern'}`} disabled={state.busy} onchange={(): void => state.updatePattern(pattern.id, 'enabled', !pattern.enabled)} />
      {/snippet}
      {#snippet actions(pattern)}
        {@const name = pattern.name || 'New pattern'}
        <Button variant="quiet" iconOnly aria-label={`Edit ${name}`} title={`Edit ${name}`} disabled={state.busy} onclick={(): void => state.editPattern(pattern.id)}>
          <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="m15 4 5 5M4 20l5-1L21 7a2.1 2.1 0 0 0-5-5L4 14z" /></svg>
        </Button>
        <Button variant="danger" iconOnly aria-label={`Delete ${name}`} title={`Delete ${name}`} disabled={state.busy} onclick={(event): Promise<void> => deletePattern(pattern.id, event.currentTarget)}>
          <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M9 6V4h6v2M5 6l1 14h12l1-14M10 10v6M14 10v6" /></svg>
        </Button>
      {/snippet}
    </AdminRecordList>
  </section>
  {/if}
  {#if section === 'patterns' && state.selected}
    {@const pattern = state.selected}
    <ModalShell title={state.creatingPattern ? 'New pattern' : 'Edit pattern'} titleId="pattern-editor-title" close={state.closeEditor} closeDisabled={state.busy} initialFocus="input" --modal-overflow="auto">
    <section aria-label="Pattern editor">
      {#if state.busy}<p role="status">Working…</p>
      {:else if state.editorMessage}<p role="status">{state.editorMessage}</p>{/if}
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
                  <Button variant="unstyled" type="button" class="remove-tag" aria-label={`Remove category ${category}`} onclick={(event): void => removeCategory(pattern.id, category, event.currentTarget)}>
                    {@render factIcon('M7 7l10 10M17 7 7 17')}
                  </Button>
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
        <Button form="pattern-category-form" disabled={state.busy || !state.editorDirty} onclick={(event): Promise<void> => savePatternEdit(pattern.id, event.currentTarget)}>Save</Button>
      </div>
    </section>
    </ModalShell>
  {/if}
{/if}

<style>
  .pattern-label { font-weight: 600; overflow-wrap: anywhere; }
  .pattern-inspection { margin-top: .75rem; padding-top: .75rem; border-top: 1px solid var(--admin-border); overflow-wrap: anywhere; }
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
  .category-tag > :global(button.remove-tag) { display: grid; place-items: center; flex: none; width: 1.5rem; height: 1.5rem; padding: 0; border: 0; border-radius: 50%; color: var(--admin-muted); background: transparent; cursor: pointer; }
  .category-tag > :global(button.remove-tag:hover) { background: var(--admin-hover); color: var(--admin-ink); }
  .category-entry { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: .5rem; }
  .polarity { text-transform: capitalize; }
  .polarity.negative { background: var(--admin-danger-bg); border-color: var(--admin-danger-border); color: var(--admin-danger-text); }
  .polarity.positive { background: var(--admin-success-bg); border-color: var(--admin-success-border); color: var(--admin-success-text); }
  fieldset { display: grid; gap: 1rem; border: 0; padding: 1rem 6px; min-width: 0; }
  h2 { margin: 0; font-size: 1.15rem; }
  .actions { display: flex; align-items: center; gap: .75rem; flex-wrap: wrap; }
  .save-actions { justify-content: flex-end; }
  .section-heading { display: flex; align-items: center; justify-content: space-between; gap: .75rem; flex-wrap: wrap; margin-bottom: .65rem; }
  .section-heading p { margin: .35rem 0 0; font-size: .9rem; color: var(--admin-muted); }
</style>
