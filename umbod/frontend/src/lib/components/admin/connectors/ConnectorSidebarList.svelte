<script lang="ts" generics="Item extends { id: string; name: string; iconDataUrl?: string }">
  import type { Snippet } from 'svelte';
  import ConnectorIcon from './ConnectorIcon.svelte';

  type Props = {
    items: Item[];
    selectedId: string;
    ariaLabel: string;
    onselect: (item: Item) => void;
    metadata: Snippet<[Item]>;
    actions: Snippet<[Item]>;
  };

  let { items, selectedId, ariaLabel, onselect, metadata, actions }: Props = $props();
</script>

<ul class="connector-list" aria-label={ariaLabel}>
  {#each items as item (item.id)}
    <li>
      <div class:connector-row-selected={selectedId === item.id} class="connector-row">
        <button type="button" aria-pressed={selectedId === item.id} onclick={() => onselect(item)}>
          <ConnectorIcon label={item.name} dataUrl={item.iconDataUrl} />
          <span class="connector-copy">
            <span class="connector-name">{item.name}</span>
            {@render metadata(item)}
          </span>
        </button>
        {@render actions(item)}
      </div>
    </li>
  {/each}
</ul>

<style>
  .connector-list { list-style: none; margin: 0; padding: 0; }
  .connector-list li { border-top: 1px solid var(--admin-border); }
  .connector-row { align-items: center; display: flex; }
  .connector-row:hover { background: var(--admin-hover); }
  .connector-row-selected, .connector-row-selected:hover { background: var(--admin-accent-soft); box-shadow: inset 2px 0 0 var(--admin-accent); }
  .connector-list .connector-row > button { align-items: flex-start; background: transparent; border: 0; color: var(--admin-ink); cursor: pointer; display: flex; font: inherit; gap: 0.6rem; min-width: 0; padding: 15px 16px; text-align: left; width: 100%; }
  .connector-copy { min-width: 0; display: grid; gap: 0.25rem; }
  .connector-name { overflow-wrap: anywhere; font-size: 13px; font-weight: 600; }
  :global(.connector-meta) { color: var(--admin-muted); font-size: 11px; overflow-wrap: anywhere; }
</style>
