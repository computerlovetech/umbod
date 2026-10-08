<script lang="ts">
  import { browserSubmit } from '$lib/admin/operations/browser-submit';
  import type { BrowserSubmitFunction as SubmitFunction } from '$lib/admin/operations/browser-submit';
  import type { Snippet } from 'svelte';

  let {
    method = 'POST',
    operation,
    enctype,
    onsubmit,
    submit,
    fields,
    actions
  }: {
    method?: 'GET' | 'POST';
    operation?: string;
    enctype?: 'application/x-www-form-urlencoded' | 'multipart/form-data' | 'text/plain';
    onsubmit?: (event: SubmitEvent) => void;
    submit?: SubmitFunction;
    fields: Snippet;
    actions?: Snippet;
  } = $props();
</script>

{#snippet content()}
  <div class="fields">
    {@render fields()}
  </div>
  {#if actions}
    <footer>
      {@render actions()}
    </footer>
  {/if}
{/snippet}

<form {method} data-operation={operation} {enctype} {onsubmit} use:browserSubmit={submit}>
  {@render content()}
</form>

<style>
  form {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-height: 0;
  }

  .fields {
    display: grid;
    gap: var(--form-gap, 1rem);
    margin-top: var(--form-margin-top, 1.25rem);
    min-height: 0;
    overflow-y: auto;
    padding: 0 0.25rem 0.25rem 0;
  }

  footer {
    align-items: center;
    background: var(--admin-panel);
    border-top: 1px solid var(--admin-border);
    display: flex;
    flex: none;
    gap: 0.75rem;
    justify-content: flex-end;
    margin-top: var(--form-actions-margin-top, 1rem);
    padding-top: 1rem;
  }
</style>
