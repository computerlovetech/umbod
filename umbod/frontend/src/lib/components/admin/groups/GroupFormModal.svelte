<script lang="ts">
  import AdminConfigurationField from '$lib/components/admin/shared/AdminConfigurationField.svelte';
  import AdminModalShell from '$lib/components/admin/shared/AdminModalShell.svelte';
  import Form from '$lib/components/admin/shared/Form.svelte';
  import LoadingButton from '$lib/components/admin/shared/LoadingButton.svelte';
  import type { GroupsState } from './groups-state.svelte';

  let { state }: { state: GroupsState } = $props();

  function inputValue(event: Event): string {
    return (event.currentTarget as HTMLInputElement | HTMLTextAreaElement).value;
  }

  function submit(event: SubmitEvent): void {
    event.preventDefault();
    void state.save();
  }
</script>

<AdminModalShell
  title={state.isEditing ? 'Edit group' : 'Create group'}
  titleId="group-form-title"
  close={state.cancel}
>
  {#snippet children()}
    {#snippet fields()}
      <fieldset disabled={state.pending}>
        <AdminConfigurationField
          id="provider-group-id"
          name="group_id"
          label="Provider group ID"
          value={state.groupId}
          readonly={state.isEditing}
          required
          helperText="Use the exact group value supplied by your identity provider, including case, punctuation and spaces. The ID cannot be changed after creation."
          oninput={(event) => state.setGroupId(inputValue(event))}
        />
        {#if !state.isEditing}
          <section class="observed-groups" aria-labelledby="observed-groups-title">
            <h3 id="observed-groups-title">Groups observed from logins</h3>
            <p>Select a group below or enter a provider group ID above.</p>
            {#if state.suggestions.options.length > 0}
              <ul>
                {#each state.suggestions.options as value (value)}
                  <li><button type="button" aria-pressed={state.groupId === value} onclick={() => state.setGroupId(value)}>{value}</button></li>
                {/each}
              </ul>
            {:else}
              <p>No observed groups to suggest. You can enter the group ID manually.</p>
            {/if}
          </section>
        {/if}
        <AdminConfigurationField
          id="group-label"
          name="label"
          label="Label"
          value={state.label}
          maxlength={200}
          required
          oninput={(event) => state.setLabel(inputValue(event))}
        />
        <div class="description-field">
          <label for="group-description">Description</label>
          <textarea
            id="group-description"
            name="description"
            value={state.description}
            maxlength="2000"
            oninput={(event) => state.setDescription(inputValue(event))}
          ></textarea>
        </div>
      </fieldset>
      {#if state.error}<p class="error" role="alert">{state.error}</p>{/if}
      {#if state.conflict}
        <LoadingButton label="Reload latest revision" loading={false} disabled={state.pending} variant="secondary" onclick={state.reloadRevision} />
      {/if}
      {#if state.message}<p class="message" role="status">{state.message}</p>{/if}
    {/snippet}
    {#snippet actions()}
      <LoadingButton label="Cancel" loading={false} disabled={state.pending} variant="secondary" onclick={state.cancel} />
      <LoadingButton type="submit" label="Save group" loadingLabel="Saving…" loading={state.pending} disabled={!state.canSave} />
    {/snippet}
    <Form onsubmit={submit} {fields} {actions} />
  {/snippet}
</AdminModalShell>

<style>
  fieldset { border: 0; display: grid; gap: 1rem; margin: 0; min-width: 0; padding: 0; }
  .observed-groups { display: grid; gap: 7px; min-width: 0; }
  .observed-groups h3 { color: var(--admin-ink); font-size: 13px; margin: 0; }
  .observed-groups p { color: var(--admin-muted); font-size: 13px; margin: 0; }
  .observed-groups ul { display: grid; gap: 4px; list-style: none; margin: 0; max-height: 160px; overflow-y: auto; padding: 3px; }
  .observed-groups button { background: var(--admin-panel); border: 1px solid var(--admin-border-strong); border-radius: var(--admin-radius); color: var(--admin-ink); cursor: pointer; font: inherit; font-size: 14px; overflow-wrap: anywhere; padding: 8px 10px; text-align: left; white-space: pre-wrap; width: 100%; }
  .observed-groups button:hover, .observed-groups button[aria-pressed="true"] { background: var(--admin-soft); border-color: var(--admin-accent); }
  .observed-groups button:focus-visible { outline: 3px solid var(--admin-focus); }
  .description-field { display: grid; gap: 7px; }
  label { color: var(--admin-ink); font-size: 13px; font-weight: 650; line-height: 1.4; }
  textarea { background: var(--admin-panel); border: 1px solid var(--admin-border-strong); border-radius: var(--admin-radius); box-sizing: border-box; color: var(--admin-ink); font: inherit; font-size: 14px; min-height: 100px; padding: 10px 12px; resize: vertical; width: 100%; }
  textarea:focus-visible { border-color: var(--admin-accent); outline: 3px solid var(--admin-focus); }
  .error { background: var(--admin-danger-bg); border-radius: 8px; color: var(--admin-danger-text); font-size: 13px; margin: 0; padding: 9px 10px; }
  .message { color: var(--admin-muted); font-size: 13px; margin: 0; }
</style>
