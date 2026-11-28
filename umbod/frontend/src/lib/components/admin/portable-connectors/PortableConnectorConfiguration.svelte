<script lang="ts">
  import { onMount } from 'svelte';
  import { portableConfigurationStatus } from '#lib/admin/unified-connectors.js';
  import TextField from '#lib/components/shared/TextField.svelte';
  import ConnectorDetailSummary from '../connectors/ConnectorDetailSummary.svelte';
  import ConnectorKindBadge from '../connectors/ConnectorKindBadge.svelte';
  import LoadingButton from '../shared/LoadingButton.svelte';
  import Select from '../shared/Select.svelte';
  import Button from '../shared/Button.svelte';
  import type { PortableConfigurationState } from './portable-configuration-state.svelte.js';

  let { state }: { state: PortableConfigurationState } = $props();
  const id = $props.id();

  onMount(() => {
    void state.load();
    return state.dispose;
  });

  function submit(event: SubmitEvent): void {
    event.preventDefault();
    void state.save();
  }
</script>

<ConnectorDetailSummary headingId={`${id}-title`} title={state.connector.name}>
  {#snippet description()}<p>{state.connector.description}</p>{/snippet}
  {#snippet statusOverview()}
    <div class="status">
      <ConnectorKindBadge label="Portable" />
      <span>{state.connector.status}</span>
      <span>{portableConfigurationStatus(state.connector.configured)}</span>
    </div>
  {/snippet}
  {#if state.status === 'loading'}
    <p role="status">Loading configuration…</p>
  {:else if state.status === 'load-error'}
    <p role="alert">Could not load the portable connector configuration.</p>
    <Button variant="secondary" onclick={state.load}>Reload configuration</Button>
  {:else}
    <h3 id={`${id}-configuration`}>Configuration</h3>
    <p class="guidance">Enter non-secret values only.</p>
    <form aria-labelledby={`${id}-configuration`} aria-busy={state.saveStatus === 'saving'} onsubmit={submit} novalidate>
      {#each state.fields as field (field.name)}
        {@const fieldId = `${id}-${field.name}`}
        {@const message = state.errorFor(field)}
        <div class="field">
          {#if field.choices.length}
            {@const value = state.value(field)}
            <Select
              id={fieldId}
              label={field.required ? `${field.label} (required)` : field.label}
              value={value === undefined ? '' : `choice:${value}`}
              options={[
                { value: '', label: field.required ? 'Choose an option' : 'No value', disabled: field.required },
                ...field.choices.map((choice) => ({ value: `choice:${choice}`, label: choice || '(Empty string)' }))
              ]}
              onchange={(choice) => state.change(field, choice === '' ? undefined : choice.slice('choice:'.length))}
              disabled={state.editingDisabled}
            />
          {:else}
            <TextField
              id={fieldId}
              label={field.label}
              value={state.value(field) ?? ''}
              required={field.required}
              disabled={state.editingDisabled}
              aria-invalid={message ? true : undefined}
              aria-describedby={message ? `${fieldId}-error` : undefined}
              oninput={(event) => state.change(field, event.currentTarget.value)}
            />
            {#if !field.required && state.value(field) !== undefined}
              <div><Button variant="quiet" size="compact" disabled={state.editingDisabled} onclick={() => state.change(field, undefined)}>Clear {field.label} value</Button></div>
            {/if}
          {/if}
          {#if message}<span class="error" id={`${fieldId}-error`} role="alert">{message}</span>{/if}
        </div>
      {:else}
        <p>No configuration fields.</p>
      {/each}
      <div class="actions">
        <LoadingButton type="submit" label="Save configuration" loadingLabel="Saving configuration" loading={state.saveStatus === 'saving'} disabled={state.editingDisabled} />
        {#if state.saveStatus === 'saved'}
          <span role="status">Configuration saved.</span>
        {:else if state.saveStatus === 'write-unconfirmed'}
          <span class="error" role="alert">Could not confirm the save. Reload the saved configuration before trying again.</span>
          <Button variant="secondary" onclick={state.load}>Reload configuration</Button>
        {:else if state.saveStatus === 'save-error'}
          <span class="error" role="alert">Could not save the configuration. Try again.</span>
        {/if}
      </div>
    </form>
  {/if}
</ConnectorDetailSummary>

<style>
  .status { align-items: center; color: var(--admin-muted); display: flex; flex-wrap: wrap; font-size: .8125rem; gap: .5rem 1rem; margin-top: 1rem; }
  h3 { font-size: 1rem; margin: 0 0 .875rem; }
  .guidance { color: var(--admin-muted); font-size: .8125rem; margin: 0 0 .875rem; }
  form { display: grid; gap: 1rem; max-width: 32rem; }
  .field { display: grid; gap: .3rem; }
  .actions { align-items: center; display: flex; flex-wrap: wrap; font-size: .8125rem; gap: .75rem; }
  .error { color: var(--admin-danger); font-size: .8125rem; }
</style>
