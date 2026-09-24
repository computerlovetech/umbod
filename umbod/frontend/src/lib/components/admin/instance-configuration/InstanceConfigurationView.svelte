<script lang="ts">
  import { BrowserClipboardWriter } from '$lib/admin/clipboard';
  import type { InstanceConfigurationPageData } from '$lib/admin/instance-configuration';
  import { useToast } from '$lib/components/feedback';
  import {
    formatConfigurationValue,
    InstanceConfigurationCopyState
  } from './instance-configuration-copy-state.svelte';

  let { state }: { state: InstanceConfigurationPageData } = $props();
  const copyState = new InstanceConfigurationCopyState(new BrowserClipboardWriter(), useToast());
</script>

<header class="page-header">
  <div>
    <p class="admin-eyebrow">Administration</p>
    <h1 class="admin-title">Configuration</h1>
    <p class="admin-lede">Effective non-secret settings used by this running instance.</p>
  </div>
</header>

{#if state.status === 'failed'}
  <section class="state-card" aria-live="polite">
    <p>{state.message}</p>
    <a class="admin-button" href="/admin/instance-configuration">{state.retryLabel}</a>
  </section>
{:else if state.status === 'empty'}
  <section class="state-card"><p>No non-secret instance configuration entries are available</p></section>
{:else}
  <div class="groups">
    {#each state.configuration.groups as group (group.id)}
      <details class="configuration-group">
        <summary>
          <span>{group.label}</span>
          <span class="entry-count">
            {group.entries.length} {group.entries.length === 1 ? 'setting' : 'settings'}
          </span>
        </summary>
        <dl>
          {#each group.entries as entry (entry.variable)}
            <div class="configuration-entry">
              <dt>
                <strong>{entry.label}</strong>
                <code class="variable">{entry.variable}</code>
              </dt>
              <dd class="description">{entry.description}</dd>
              <dd class="value-row">
                <code class="value">
                  {#if entry.type === 'string_list' && entry.value.length === 0}
                    <span class="empty">None</span>
                  {:else if entry.type === 'string' && entry.value === ''}
                    <span class="empty">Empty</span>
                  {:else}
                    {formatConfigurationValue(entry)}
                  {/if}
                </code>
                <button
                  class="copy-value"
                  type="button"
                  aria-label={`Copy value for ${entry.label}`}
                  onclick={() => copyState.copyEntry(entry)}
                >
                  {copyState.copiedTarget === entry.variable ? 'Copied' : 'Copy value'}
                </button>
              </dd>
            </div>
          {/each}
        </dl>
      </details>
    {/each}
  </div>
{/if}

<style>
  .page-header {
    align-items: end;
    display: flex;
    gap: 24px;
    justify-content: space-between;
    margin-bottom: 24px;
  }
  .page-header :global(.admin-lede) {
    margin-bottom: 0;
  }
  button {
    font: inherit;
  }
  .copy-value {
    background: var(--admin-surface);
    border: 1px solid var(--admin-border);
    border-radius: 7px;
    color: inherit;
    cursor: pointer;
    font-weight: 600;
  }
  .copy-value {
    font-size: 12px;
    padding: 6px 9px;
  }
  .copy-value:hover {
    border-color: var(--admin-muted);
  }
  .copy-value:focus-visible,
  summary:focus-visible {
    outline: 2px solid currentColor;
    outline-offset: 3px;
  }
  .groups {
    display: grid;
    gap: 16px;
  }
  .configuration-group {
    background: var(--admin-surface);
    border: 1px solid var(--admin-border);
    border-radius: 10px;
    padding: 0 22px;
  }
  summary {
    cursor: pointer;
    font-size: 17px;
    font-weight: 650;
    padding: 18px 0;
  }
  summary::marker {
    color: var(--admin-muted);
  }
  .entry-count {
    color: var(--admin-muted);
    float: right;
    font-size: 13px;
    font-weight: 400;
    margin-top: 3px;
  }
  dl {
    margin: 0;
  }
  .configuration-group[open] dl {
    border-top: 1px solid var(--admin-border);
  }
  .configuration-entry {
    border-bottom: 1px solid var(--admin-border);
    display: grid;
    gap: 6px;
    padding: 18px 0;
  }
  .configuration-entry:last-child {
    border-bottom: 0;
  }
  dt {
    align-items: baseline;
    display: flex;
    flex-wrap: wrap;
    gap: 7px 12px;
  }
  dt strong {
    font-size: 15px;
  }
  dd {
    margin: 0;
  }
  .description {
    color: var(--admin-muted);
    font-size: 13px;
  }
  .variable {
    color: var(--admin-muted);
    font-size: 12px;
  }
  .value-row {
    align-items: center;
    display: flex;
    gap: 10px;
    justify-content: space-between;
    margin-top: 4px;
    min-width: 0;
  }
  code {
    background: var(--admin-accent-soft);
    border-radius: 5px;
    padding: 3px 6px;
  }
  .value {
    font-size: 14px;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
  }
  .empty {
    color: var(--admin-muted);
    font-style: italic;
  }
  .state-card {
    border: 1px solid var(--admin-border);
    border-radius: 10px;
    padding: 22px;
  }
  .admin-button {
    display: inline-block;
    margin-top: 12px;
  }
  @media (max-width: 640px) {
    .page-header {
      align-items: stretch;
      flex-direction: column;
    }
    .value-row {
      align-items: start;
      flex-direction: column;
    }
  }
</style>
