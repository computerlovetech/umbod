<script lang="ts" generics="Item extends { id: string; name: string; iconDataUrl?: string }">
  import type { Snippet } from 'svelte';
  import ConnectorIcon from './ConnectorIcon.svelte';

  type LinkItem = { href: string; name: string; iconDataUrl?: string; label: string };

  type Props = {
    items: readonly Item[];
    linkedItems?: readonly LinkItem[];
    selectedId?: string;
    ariaLabel: string;
    onselect: (item: Item) => void;
    metadata: Snippet<[Item]>;
    actions: Snippet<[Item]>;
  };

  let { items, linkedItems, selectedId, ariaLabel, onselect, metadata, actions }: Props = $props();
  const rows = $derived(linkedItems === undefined
    ? items.map((item) => ({ key: `item:${item.id}`, name: item.name, item }))
    : [
        ...items.map((item) => ({ key: `item:${item.id}`, name: item.name, item })),
        ...linkedItems.map((link) => ({ key: `link:${link.href}`, name: link.name, link }))
      ].sort((left, right) => left.name.localeCompare(right.name)));
</script>

<ul class="connector-list" aria-label={ariaLabel}>
  {#each rows as row (row.key)}
    <li>
      {#if 'item' in row}
        {@const item = row.item}
        <div class={['connector-row', selectedId === item.id && 'connector-row-selected']}>
          <button type="button" aria-pressed={selectedId === item.id} onclick={() => onselect(item)}>
            <ConnectorIcon label={item.name} dataUrl={item.iconDataUrl} />
            <span class="connector-copy">
              <span class="connector-name">{item.name}</span>
              {@render metadata(item)}
            </span>
          </button>
          {@render actions(item)}
        </div>
      {:else}
        <div class="connector-row">
          <a href={row.link.href}>
            <ConnectorIcon label={row.link.name} dataUrl={row.link.iconDataUrl} />
            <span class="connector-copy">
              <span class="connector-name">{row.link.name}</span>
              <span class="connector-meta">{row.link.label}</span>
            </span>
          </a>
        </div>
      {/if}
    </li>
  {/each}
</ul>

<style>
  .connector-list { list-style: none; margin: 0; padding: 0; }
  .connector-list li { border-top: 1px solid var(--admin-border); }
  .connector-row { align-items: center; display: flex; }
  .connector-row:hover { background: var(--admin-hover); }
  .connector-row-selected, .connector-row-selected:hover { background: var(--admin-accent-soft); box-shadow: inset 2px 0 0 var(--admin-accent); }
  .connector-list .connector-row > :is(button, a) { align-items: flex-start; background: transparent; border: 0; color: var(--admin-ink); cursor: pointer; display: flex; font: inherit; gap: 0.6rem; min-width: 0; padding: 15px 16px; text-align: left; width: 100%; }
  .connector-row > a { box-sizing: border-box; text-decoration: none; }
  .connector-copy { min-width: 0; display: grid; gap: 0.25rem; }
  .connector-name { overflow-wrap: anywhere; font-size: 13px; font-weight: 600; }
  :global(.connector-meta) { color: var(--admin-muted); font-size: 11px; overflow-wrap: anywhere; }
</style>
