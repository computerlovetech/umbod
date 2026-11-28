<script lang="ts">
  import { tick } from 'svelte';
  import ModalShell from '#lib/components/shared/ModalShell.svelte';
  import PlusIcon from '#lib/components/shared/PlusIcon.svelte';
  import TextAreaField from '#lib/components/shared/TextAreaField.svelte';
  import AdminSettingsActions from '../shared/AdminSettingsActions.svelte';
  import Button from '../shared/Button.svelte';
  import Select from '../shared/Select.svelte';
  import type { ProviderGroupMappingsState } from './provider-group-mappings-state.svelte';

  let { state }: { state: ProviderGroupMappingsState } = $props();

  const editorId = $props.id();
  const addButtonId = `${editorId}-add-mapping`;
  const saveButtonId = `${editorId}-save`;
  const saveStatusId = `${editorId}-status`;

  async function cancelConfirmation(): Promise<void> {
    const wasConfirmingSave = state.saveConfirmationOpen;
    state.cancelConfirmation();
    if (!wasConfirmingSave) return;
    await tick();
    document.getElementById(saveButtonId)?.focus();
  }

  async function confirmSave(): Promise<void> {
    void state.confirmSave();
    await tick();
    document.getElementById(saveStatusId)?.focus();
  }

  async function confirmRemoval(): Promise<void> {
    state.confirmRemoval();
    await tick();
    document.getElementById(addButtonId)?.focus();
  }
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
  {#if state.catalogueStatus === 'loading'}
    <p role="status">Loading registered groups…</p>
  {:else if state.catalogueStatus === 'failed'}
    <div class="catalogue-error">
      <p role="alert">Could not load registered groups.</p>
      <Button variant="secondary" size="compact" onclick={state.loadGroups}>Retry loading groups</Button>
    </div>
  {/if}

  <div class="mappings">
    {#if state.rows.length > 0}
      <div class="mapping-list">
        {#each state.rows as { id, mapping }, index (id)}
          {@const removeLabel = `Remove mapping ${index + 1}`}
          <fieldset>
            <legend>Mapping {index + 1}</legend>
            <div class="mapping-row mapping-row--editable">
              <div class="fields">
                <TextAreaField id={`${editorId}-${id}-provider-value`} label="Provider value" rows={1} value={mapping.external_value} readonly={!state.editable} oninput={(event): void => state.change(id, 'external_value', event.currentTarget.value)} />
                <Select options={state.groupOptions(mapping.group_id)} label="Umbod group" value={mapping.group_id} disabled={!state.editable} onchange={(value): void => state.change(id, 'group_id', value)} />
              </div>
              <div class="row-action">
                <Button variant="danger" size="compact" iconOnly aria-label={removeLabel} title={removeLabel} disabled={!state.editable} onclick={(): void => state.requestRemoval(id)}>
                  <svg aria-hidden="true" focusable="false" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M9 6V4h6v2M5 6l1 14h12l1-14M10 10v6M14 10v6" /></svg>
                </Button>
              </div>
            </div>
          </fieldset>
        {/each}
      </div>
    {:else}
      <p>No mappings.</p>
    {/if}
  </div>

  <Button id={addButtonId} disabled={!state.editable} onclick={state.add}><PlusIcon />Add mapping</Button>
  {#if state.validationMessage}
    <p class="validation" role="status">{state.validationMessage}</p>
  {/if}
  <AdminSettingsActions busy={state.busy} dirty={state.dirty} saveDisabled={!state.canSave} {saveButtonId} statusId={saveStatusId} onDiscard={state.discard} onSave={state.requestSave} />
{/if}

{#if state.removalTarget || state.saveConfirmationOpen}
  {@const removalTarget = state.removalTarget}
  <ModalShell title={removalTarget ? 'Delete mapping?' : 'Save group mapping changes?'} titleId={`${editorId}-confirmation-title`} descriptionId={`${editorId}-confirmation-description`} close={cancelConfirmation} role="alertdialog" --modal-width="28rem" --modal-overflow="auto">
    <div class="mapping-warning" id={`${editorId}-confirmation-description`}>
      <svg aria-hidden="true" focusable="false" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M10.3 4.6 2.6 18a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 4.6a2 2 0 0 0-3.4 0ZM12 9v4m0 4h.01" /></svg>
      <div>
        {#if removalTarget}
          {#if removalTarget.mapping.external_value}
            <p class="delete-target">Provider value: <strong>{removalTarget.mapping.external_value}</strong></p>
          {/if}
          {#if state.removalGroupLabel}
            <p class="delete-target">Umbod group: <strong>{state.removalGroupLabel}</strong></p>
          {/if}
          <p>Users who rely on this mapping may lose access to the Umbod group after you save changes.</p>
        {:else}
          <p>These changes affect authorization across the instance. Users may gain or lose access to Umbod groups.</p>
        {/if}
      </div>
    </div>
    <div class="confirmation-actions">
      <Button variant="secondary" data-dialog-cancel onclick={cancelConfirmation}>Cancel</Button>
      {#if removalTarget}
        <Button variant="danger" onclick={confirmRemoval}>Delete mapping</Button>
      {:else}
        <Button onclick={confirmSave}>Save group mappings</Button>
      {/if}
    </div>
  </ModalShell>
{/if}

<style>
  p { color: var(--admin-muted); font-size: 13px; line-height: 1.5; margin: 0; }
  .catalogue-error { align-items: center; display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.75rem; }
  .mapping-warning { align-items: flex-start; background: var(--admin-warning-bg); border: 1px solid var(--admin-warning-border); border-radius: var(--admin-radius); color: var(--admin-warning-text); display: flex; gap: 0.75rem; margin: 1rem 0; padding: 0.75rem; }
  .mapping-warning svg { flex: none; }
  .mapping-warning p { color: inherit; overflow-wrap: anywhere; }
  .delete-target { margin-bottom: 0.25rem; white-space: pre-wrap; }
  .confirmation-actions { display: flex; flex-wrap: wrap; gap: 0.5rem; justify-content: flex-end; }
  .mappings { container-type: inline-size; display: grid; gap: 0.5rem; margin: 0.875rem 0; }
  .mapping-list { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius-panel); min-width: 0; }
  fieldset { border: 0; margin: 0; min-width: 0; padding: 0; }
  fieldset + fieldset { border-top: 1px solid var(--admin-border); }
  legend { clip-path: inset(50%); height: 1px; overflow: hidden; padding: 0; position: absolute; white-space: nowrap; width: 1px; }
  .mapping-row { display: grid; gap: 0.75rem; grid-template-columns: minmax(0, 1fr) auto; padding: 0.65rem 0.75rem; }
  .fields { align-items: start; display: grid; gap: 0.75rem; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 0; }
  .row-action { justify-self: end; }
  .mapping-row--editable { --mapping-label-height: 1.125rem; --mapping-label-gap: 0.25rem; align-items: start; }
  .mapping-row--editable .row-action { margin-top: calc(var(--mapping-label-height) + var(--mapping-label-gap) + 0.25rem); }
  .mapping-row--editable :global(.form-field), .mapping-row--editable :global(.select) { gap: var(--mapping-label-gap); }
  .mapping-row--editable :global(label) { font-size: 0.8125rem; font-weight: 650; line-height: var(--mapping-label-height); }
  .mapping-row--editable :global(textarea.form-control), .mapping-row--editable :global(.select .trigger) {
    box-sizing: border-box;
    font-size: 0.875rem;
    line-height: 1.25rem;
    min-height: 2.25rem;
    padding: 0.4375rem 0.6rem;
  }
  .mapping-row--editable :global(.select .trigger) { overflow-wrap: anywhere; }
  @container (max-width: 28.75rem) {
    .fields { gap: 0.5rem; grid-template-columns: minmax(0, 1fr); }
  }
  .validation { color: var(--admin-warning-text); margin-top: 0.75rem; }
</style>
