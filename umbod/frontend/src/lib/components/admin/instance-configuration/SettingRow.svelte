<script lang="ts">
  import type { PresentedSetting } from './presentation';
  import { formatConfigurationValue, type InstanceConfigurationCopyState } from './instance-configuration-copy-state.svelte';

  let { setting, copyState }: { setting: PresentedSetting; copyState: InstanceConfigurationCopyState } = $props();
</script>

<div class={['setting-row', setting.address && 'address-row']}>
  <dt>{setting.label}</dt>
  <dd class="display-value">
    {#each setting.values as value, index (`${index}:${value}`)}
      <span>{value}</span>
    {/each}
    {#if setting.address}
      <button class="admin-button" type="button" aria-label={`Copy ${setting.label.toLowerCase()}`} onclick={() => copyState.copyEntry(setting.entry)}>
        {copyState.isCopied(setting.entry) ? 'Copied' : 'Copy address'}
      </button>
    {/if}
  </dd>
  <dd class="explanation">{setting.description}</dd>
  <dd>
    <details class="technical">
      <summary>Technical details</summary>
      <p><strong>{setting.entry.label}</strong></p>
      <p><code>{setting.entry.variable}</code></p>
      <p>{setting.entry.description}</p>
      <p class="raw-value"><strong>Raw value</strong> <code>{formatConfigurationValue(setting.entry)}</code></p>
      <button class="copy-value" type="button" aria-label={`Copy raw value for ${setting.label}`} onclick={() => copyState.copyEntry(setting.entry)}>{copyState.isCopied(setting.entry) ? 'Copied' : 'Copy raw value'}</button>
    </details>
  </dd>
</div>

<style>
  .setting-row { border-top: 1px solid var(--admin-border); display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 8px; padding: 18px 0; min-width: 0; }
  dt { align-self: center; font-weight: 600; font-size: 15px; }
  dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
  dd:not(.display-value) { grid-column: 1 / -1; }
  .display-value { display: flex; align-items: end; flex-direction: column; gap: 8px; font-size: 16px; text-align: right; }
  .address-row .display-value { grid-column: 1 / -1; flex-direction: row; align-items: center; justify-content: space-between; flex-wrap: wrap; text-align: left; }
  .address-row .display-value span { flex: 1 1 220px; min-width: 0; }
  @media (max-width: 640px) { .setting-row { grid-template-columns: minmax(0, 1fr); } .display-value { align-items: start; text-align: left; } }
  .explanation, .technical { color: var(--admin-muted); font-size: 13px; line-height: 1.6; }
  summary { cursor: pointer; width: fit-content; }
  code { font-family: var(--admin-mono); white-space: pre-wrap; overflow-wrap: anywhere; }
  .raw-value code { display: block; min-height: 1.6em; }
  button { font: inherit; cursor: pointer; }
  .copy-value { background: var(--admin-soft); color: var(--admin-ink); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: 6px 10px; }
  button:focus-visible, summary:focus-visible { outline: 3px solid var(--admin-focus); outline-offset: 3px; }
</style>
