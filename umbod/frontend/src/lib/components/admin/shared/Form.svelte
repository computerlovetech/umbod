<script lang="ts">
  import { enhance } from '$app/forms';
  import type { SubmitFunction } from '@sveltejs/kit';
  import type { Snippet } from 'svelte';

  let {
    method = 'POST',
    action,
    enctype,
    onsubmit,
    submit,
    fields,
    actions
  }: {
    method?: 'GET' | 'POST';
    action?: string;
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

{#if submit}
  <form {method} {action} {enctype} {onsubmit} use:enhance={submit}>
    {@render content()}
  </form>
{:else}
  <form {method} {action} {enctype} {onsubmit}>
    {@render content()}
  </form>
{/if}

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
    background: #fff;
    border-top: 1px solid #e9e9e7;
    display: flex;
    flex: none;
    gap: 0.75rem;
    justify-content: flex-end;
    margin-top: var(--form-actions-margin-top, 1rem);
    padding-top: 1rem;
  }
</style>
