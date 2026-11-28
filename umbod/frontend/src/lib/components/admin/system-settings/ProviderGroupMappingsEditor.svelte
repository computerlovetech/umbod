<script lang="ts">
  import TextAreaField from '#lib/components/shared/TextAreaField.svelte';
  import AdminSettingsActions from '../shared/AdminSettingsActions.svelte';
  import Button from '../shared/Button.svelte';
  import Select from '../shared/Select.svelte';
  import type { ProviderGroupMappingsState } from './provider-group-mappings-state.svelte';

  let { state }: { state: ProviderGroupMappingsState } = $props();

  const editorId = $props.id();
</script>

{#if state.loading}
  <p role="status">Loading provider group mappings…</p>
{/if}
{#if state.failure}
  <p class="admin-message admin-message--error" role="alert">{state.failure}</p>
{/if}
{#if state.canRetry}
  <Button variant="secondary" onclick={state.load}>Try again</Button>
{/if}

{#if state.ready}
  <div class="toolbar">
    <span class="source">{state.sourceLabel}</span>
    {#if state.canReset}
      <Button variant="quiet" size="compact" disabled={state.busy} onclick={state.reset}>Clear saved overrides</Button>
    {/if}
  </div>
  {#if state.resetting}
    <p role="status">Save changes to remove all explicit mappings.</p>
  {/if}
  {#if state.catalogueStatus === 'loading'}
    <p role="status">Loading registered groups…</p>
  {:else if state.catalogueStatus === 'failed'}
    <div class="catalogue-error">
      <p role="alert">Could not load registered groups.</p>
      <Button variant="secondary" size="compact" onclick={state.loadGroups}>Retry loading groups</Button>
    </div>
  {/if}

  <p>Values without a matching explicit rule still use inherited OAuth mappings when configured.</p>
  {#if state.inheritedRows.length > 0}
    <div class="mappings">
      <h3>Inherited suggestions</h3>
      {#each state.inheritedRows as { id, mapping }, index (id)}
        <fieldset>
          <legend>Inherited mapping {index + 1}</legend>
          <dl class="fields">
            <div><dt>Provider value</dt><dd>{mapping.external_value}</dd></div>
            <div><dt>Umbod group</dt><dd>{mapping.group_id}</dd></div>
          </dl>
          <div class="row-actions">
            {#if state.isOverridden(mapping.external_value)}
              <p>Override added</p>
            {:else}
              <Button variant="quiet" size="compact" aria-label={`Override inherited mapping ${index + 1}`} disabled={!state.editable} onclick={(): void => state.addOverride(id)}>Override</Button>
            {/if}
          </div>
        </fieldset>
      {/each}
    </div>
  {/if}

  <div class="mappings">
    <h3>Explicit mappings</h3>
    {#each state.rows as { id, mapping }, index (id)}
      <fieldset>
        <legend>Mapping {index + 1}</legend>
        <div class="fields">
          <TextAreaField id={`${editorId}-${id}-provider-value`} label="Provider value" rows={1} value={mapping.external_value} readonly={!state.editable} oninput={(event): void => state.change(id, 'external_value', event.currentTarget.value)} />
          <Select options={state.groupOptions(mapping.group_id)} label="Umbod group" value={mapping.group_id} disabled={!state.editable} onchange={(value): void => state.change(id, 'group_id', value)} />
        </div>
        <div class="row-actions">
          <Button variant="quiet" size="compact" aria-label={`Remove mapping ${index + 1}`} disabled={!state.editable} onclick={(): void => state.remove(id)}>Remove</Button>
        </div>
      </fieldset>
    {:else}
      <p>No explicit mappings.</p>
    {/each}
  </div>

  <Button variant="secondary" size="compact" disabled={!state.editable} onclick={state.add}>Add mapping</Button>
  {#if state.validationMessage}
    <p class="validation" role="status">{state.validationMessage}</p>
  {/if}
  <AdminSettingsActions busy={state.busy} dirty={state.dirty} saveDisabled={!state.canSave} onDiscard={state.discard} onSave={state.save} />
{/if}

<style>
  p { color: var(--admin-muted); font-size: 13px; line-height: 1.5; margin: 0; }
  .toolbar, .catalogue-error { align-items: center; display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.75rem; }
  .source { background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: 999px; color: var(--admin-muted); font-size: 11px; padding: 3px 8px; }
  .mappings { display: grid; gap: 0.875rem; margin: 0.875rem 0; }
  fieldset { border: 1px solid var(--admin-border); border-radius: var(--admin-radius); margin: 0; min-width: 0; padding: 0.75rem; }
  legend { color: var(--admin-muted); font-size: 12px; padding: 0 0.375rem; }
  .fields { display: grid; gap: 0.75rem; grid-template-columns: repeat(auto-fit, minmax(min(100%, 15rem), 1fr)); }
  h3 { font-size: 14px; margin: 0; }
  dl { margin: 0; }
  dt { font-size: 0.8125rem; font-weight: 600; }
  dd { font-size: 13px; margin: 0.35rem 0 0; overflow-wrap: anywhere; white-space: pre-wrap; }
  .row-actions { display: flex; justify-content: flex-end; margin-top: 0.5rem; }
  .validation { color: var(--admin-warning-text); margin-top: 0.75rem; }
</style>
