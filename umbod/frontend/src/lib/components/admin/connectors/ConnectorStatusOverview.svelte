<script module lang="ts">
  import type { Snippet } from 'svelte';

  const iconPaths = {
    shared: 'M12 20v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m15-6a4 4 0 0 1 5 4v2M15 4a4 4 0 0 1 0 8M7 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
    personal: 'M4 21v-2a5 5 0 0 1 5-5h6a5 5 0 0 1 5 5v2m-4-13a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
    check: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM8 12l2.5 2.5L16 9',
    failed: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM9 9l6 6m0-6-6 6',
    unknown: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-11-3a2 2 0 1 1 3.4 1.4c-.7.6-1.4 1.1-1.4 2.6m0 3h.01',
    open: 'M7 11V7a5 5 0 0 1 9-3m-4 11v2M7 11h10a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-6a2 2 0 0 1 2-2Z',
    lock: 'M7 11V8a5 5 0 0 1 10 0v3m-5 4v2M7 11h10a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-6a2 2 0 0 1 2-2Z',
    warning: 'M10.3 4.5 2.6 18A1.6 1.6 0 0 0 4 20.4h16a1.6 1.6 0 0 0 1.4-2.4L13.7 4.5a2 2 0 0 0-3.4 0ZM12 9v4m0 3v.3',
    tools: 'M8 7V4h8v3M3 12h18m-12 0v2m6-2v2M5 7h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2Z',
    calendar: 'M8 3v4m8-4v4M3 10h18m-13 5h2m4 0h2M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z',
    source: 'm12 3 9 5v8l-9 5-9-5V8l9-5Zm0 9 9-4m-9 4L3 8m9 4v9'
  } as const;

  type Tone = 'neutral' | 'success' | 'warning' | 'danger';

  export type ConnectorStatusEntry = {
    label: string;
    value: string | Snippet;
    icon: keyof typeof iconPaths;
    tone?: Tone;
  };

  export type ConnectorStatusSpotlight = ConnectorStatusEntry & {
    tone: Tone;
  };
</script>

<script lang="ts">
  let { spotlight, entries }: { spotlight?: ConnectorStatusSpotlight; entries: readonly ConnectorStatusEntry[] } = $props();
</script>

{#snippet entry(item: ConnectorStatusEntry)}
  <dt>
    <span class="icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" focusable="false"><path d={iconPaths[item.icon]} /></svg>
    </span>
    {item.label}
  </dt>
  <dd>{#if typeof item.value === 'string'}{item.value}{:else}{@render item.value()}{/if}</dd>
{/snippet}

<div class="status-overview">
  <div class={['layout', { 'has-spotlight': spotlight && entries.length > 0 }]}>
    {#if spotlight}
      <dl class="spotlight" data-tone={spotlight.tone} aria-label="Status spotlight">
        <div>{@render entry(spotlight)}</div>
      </dl>
    {/if}
    {#if entries.length}
      <dl class="context" aria-label="Connector indicators">
        {#each entries as item (item.label)}
          <div data-tone={item.tone}>{@render entry(item)}</div>
        {/each}
      </dl>
    {/if}
  </div>
</div>

<style>
  .status-overview { border-block: 1px solid var(--admin-border); container-type: inline-size; margin-top: 1.25rem; padding-block: 0.85rem; }
  .layout { display: grid; gap: 0.65rem; }
  .has-spotlight { grid-template-columns: minmax(0, 1fr) minmax(0, 1.85fr); }
  dl { border-radius: 8px; margin: 0; min-width: 0; padding: 0.7rem 0.8rem; }
  dl > div { min-width: 0; position: relative; }
  dt { color: var(--admin-muted); font-size: 0.75rem; font-weight: 650; }
  dd { font-size: 0.875rem; font-weight: 650; margin: 0; overflow-wrap: anywhere; }
  .icon { display: grid; inset-inline-start: 0; place-items: center; position: absolute; top: 50%; translate: 0 -50%; }
  svg { height: 1rem; width: 1rem; }
  .spotlight { --signal-ink: var(--admin-muted); --signal-bg: var(--admin-soft); align-content: center; background: var(--signal-bg); border-inline-start: 3px solid var(--signal-ink); color: var(--signal-ink); display: grid; }
  .spotlight[data-tone='success'] { --signal-ink: var(--admin-success-text); --signal-bg: var(--admin-success-bg); }
  .spotlight[data-tone='warning'] { --signal-ink: var(--admin-warning-text); --signal-bg: var(--admin-warning-bg); }
  .spotlight[data-tone='danger'] { --signal-ink: var(--admin-danger-text); --signal-bg: var(--admin-danger-bg); }
  .spotlight > div { padding-inline-start: 2.85rem; }
  .spotlight dd { font-size: 1rem; }
  .spotlight .icon { background: var(--admin-panel); border-radius: 50%; color: var(--signal-ink); height: 2.25rem; width: 2.25rem; }
  .spotlight svg { height: 1.25rem; width: 1.25rem; }
  .context { align-items: center; border: 1px solid var(--admin-border); display: flex; flex-wrap: wrap; gap: 0.55rem 1rem; }
  .context > div { padding-inline-start: 1.4rem; }
  .context .icon { color: var(--admin-muted); }
  .context [data-tone='danger'] :is(.icon, dd) { color: var(--admin-danger-text); }
  .context [data-tone='warning'] :is(.icon, dd) { color: var(--admin-warning-text); }
  @container (max-width: 35rem) {
    .has-spotlight { grid-template-columns: minmax(0, 1fr); }
  }
</style>
