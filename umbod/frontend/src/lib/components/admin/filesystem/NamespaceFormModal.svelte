<script lang="ts">
  import TextField from '#lib/components/shared/TextField.svelte';
  import Button from '../shared/Button.svelte';
  import Form from '../shared/Form.svelte';
  import LoadingButton from '../shared/LoadingButton.svelte';
  import ModalShell from '#lib/components/shared/ModalShell.svelte';
  import type { NamespaceManagementState } from './namespace-management-state.svelte';

  let { state }: { state: NamespaceManagementState } = $props();
  const id = $props.id();

  function submit(event: SubmitEvent): void {
    event.preventDefault();
    void state.save();
  }
</script>

<ModalShell title={state.selected ? 'Edit namespace' : 'New namespace'} titleId={id + '-title'} close={state.closeEditor} closeDisabled={state.busy} initialFocus="input[name='namespace_name']">
  {#snippet children()}
    {#snippet fields()}
      <fieldset disabled={state.busy}>
        <TextField id={id + '-namespace-name'} name="namespace_name" label="Name" value={state.name} autocomplete="off" data-1p-ignore="true" required maxlength={255} oninput={(event) => state.changeName(event.currentTarget.value)} />
        <div class="description-field">
          <label for={id + '-description'}>Description <span>(optional)</span></label>
          <textarea id={id + '-description'} name="namespace_description" value={state.description} rows="4" oninput={(event) => state.changeDescription(event.currentTarget.value)}></textarea>
        </div>
      </fieldset>
      {#if state.error}<p class="error" role="alert">{state.error}</p>{/if}
      {#if state.conflict}<Button variant="secondary" disabled={state.busy} onclick={state.refreshConflict}>Refresh revision</Button>{/if}
    {/snippet}
    {#snippet actions()}
      <Button variant="secondary" disabled={state.busy} onclick={state.closeEditor}>Cancel</Button>
      <LoadingButton type="submit" label={state.selected ? 'Save changes' : 'Create namespace'} loadingLabel="Saving namespace" loading={state.busy} disabled={!state.canSave} />
    {/snippet}
    <Form aria-label="Namespace" onsubmit={submit} {fields} {actions} />
  {/snippet}
</ModalShell>

<style>
  .description-field { display: grid; gap: 7px; margin-top: 1rem; }
  label { color: var(--admin-ink); font-size: 13px; font-weight: 650; line-height: 1.4; }
  label span { color: var(--admin-muted); font-weight: 400; }
  textarea { background: var(--admin-panel); border: 1px solid var(--admin-border-strong); border-radius: var(--admin-radius); box-sizing: border-box; color: var(--admin-ink); font: inherit; font-size: 14px; min-width: 0; padding: 10px 12px; resize: vertical; width: 100%; }
  textarea:focus-visible { border-color: var(--admin-accent); outline: 3px solid var(--admin-focus); }
  textarea:disabled { background: var(--admin-soft); }
  fieldset { border: 0; margin: 0; min-width: 0; padding: 0; }
  .error { background: var(--admin-danger-bg); border-radius: var(--admin-radius); color: var(--admin-danger-text); font-size: 0.875rem; margin: 0; padding: 0.75rem; }
</style>
