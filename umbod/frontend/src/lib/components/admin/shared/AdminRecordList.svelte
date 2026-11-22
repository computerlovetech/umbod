<script lang="ts" generics="T">
  import type { Snippet } from 'svelte';

  interface Props {
    items: readonly T[];
    keyOf: (item: T) => string;
    label: string;
    recordHeading: string;
    detailHeading: string;
    emptyMessage: string;
    identity: Snippet<[T]>;
    detail: Snippet<[T]>;
    actions: Snippet<[T]>;
  }

  let { items, keyOf, label, recordHeading, detailHeading, emptyMessage, identity, detail, actions }: Props = $props();
</script>

<div class="record-panel">
  <div class="record-header" aria-hidden="true">
    <span>{recordHeading}</span>
    <span class="detail-heading">{detailHeading}</span>
    <span class="actions-heading">Actions</span>
  </div>
  <ul aria-label={label} role="list">
    {#each items as item (keyOf(item))}
      <li class="record-row">
        <div class="record-identity">{@render identity(item)}</div>
        <div class="record-detail">{@render detail(item)}</div>
        <div class="record-actions">{@render actions(item)}</div>
      </li>
    {:else}
      <li class="empty">{emptyMessage}</li>
    {/each}
  </ul>
</div>

<style>
  .record-panel {
    background: var(--admin-panel);
    border: 1px solid var(--admin-border);
    border-radius: var(--admin-radius-panel);
    container-type: inline-size;
    min-width: 0;
  }

  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .record-header,
  .record-row {
    align-items: center;
    display: grid;
    gap: 1rem;
    grid-template-columns: minmax(0, 1fr) minmax(8rem, 25%) 5.5rem;
    padding: 0.9rem 1.15rem;
  }

  .record-header {
    background: var(--admin-soft);
    border-start-end-radius: calc(var(--admin-radius-panel) - 1px);
    border-start-start-radius: calc(var(--admin-radius-panel) - 1px);
    color: var(--admin-muted);
    font-size: 0.8rem;
    font-weight: 650;
  }

  .record-row,
  .empty {
    border-top: 1px solid var(--admin-border);
  }

  .record-header > span,
  .record-identity,
  .record-detail {
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .actions-heading {
    text-align: end;
  }

  .record-actions {
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    gap: 0.55rem;
    justify-content: flex-end;
  }

  .empty {
    color: var(--admin-muted);
    padding: 1.15rem;
  }

  @container (max-width: 28.75rem) {
    .record-header,
    .record-row {
      gap: 0.55rem;
      grid-template-columns: minmax(0, 1fr) 5.5rem;
      padding-inline: 0.7rem;
    }

    .detail-heading {
      display: none;
    }

    .record-detail {
      grid-row: 2;
    }

    .record-actions {
      grid-column: 2;
      grid-row: 1 / 3;
    }
  }
</style>
