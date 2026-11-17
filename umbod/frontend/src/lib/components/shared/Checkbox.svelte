<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLInputAttributes } from 'svelte/elements';

  let { id, label, labelContent, checked, ...attributes }: Omit<HTMLInputAttributes, 'id' | 'type' | 'children' | 'checked'> & {
    id: string;
    label: string;
    labelContent?: Snippet;
    checked: boolean;
  } = $props();
</script>

<label for={id}>
  <input type="checkbox" {...attributes} {id} {checked} />
  <span>
    {#if labelContent}
      {@render labelContent()}
    {:else}
      {label}
    {/if}
  </span>
</label>

<style>
  label {
    align-items: flex-start;
    border: 1px solid var(--admin-border);
    border-radius: var(--admin-radius);
    color: var(--admin-ink);
    cursor: pointer;
    display: flex;
    gap: 10px;
    line-height: 1.5;
    padding: 10px 12px;
  }

  input {
    accent-color: var(--admin-accent);
    cursor: inherit;
    flex: none;
    height: 16px;
    margin: 3px 0 0;
    width: 16px;
  }

  input:focus-visible {
    outline: 3px solid var(--admin-focus);
    outline-offset: 3px;
  }

  span {
    min-width: 0;
    overflow-wrap: anywhere;
  }

  label:has(input:disabled) {
    color: var(--admin-muted);
    cursor: not-allowed;
    opacity: 0.72;
  }
</style>
