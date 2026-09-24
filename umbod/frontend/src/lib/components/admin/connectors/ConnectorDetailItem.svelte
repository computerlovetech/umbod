<script lang="ts">
  import type { Snippet } from 'svelte';

  type Tone = 'neutral' | 'success' | 'warning' | 'danger';
  type Variant = 'summary' | 'detail';

  type Props = {
    label: string;
    children: Snippet;
    tone?: Tone;
    variant?: Variant;
  };

  let { label, children, tone = 'neutral', variant = 'summary' }: Props = $props();
  const indicator = $derived(tone === 'success' ? '✓' : tone === 'warning' ? '!' : tone === 'danger' ? '×' : '•');
</script>

<div class={`detail-item ${variant}`} data-tone={tone}>
  <dt>{label}</dt>
  <dd>
    {#if variant === 'summary'}<span class="indicator" aria-hidden="true">{indicator}</span>{/if}
    <span class="value">{@render children()}</span>
  </dd>
</div>

<style>
  .detail-item { min-width: 0; }
  dt { color: #787774; font-size: 0.72rem; font-weight: 650; letter-spacing: 0.04em; margin-bottom: 0.3rem; text-transform: uppercase; }
  dd { color: #37352f; font-size: 0.9rem; line-height: 1.45; margin: 0; min-width: 0; overflow-wrap: anywhere; }
  .summary dd { align-items: center; display: flex; font-weight: 600; gap: 0.45rem; }
  .indicator { align-items: center; background: #f1f1ef; border-radius: 50%; color: #6b6964; display: inline-flex; flex: 0 0 auto; font-size: 0.72rem; font-weight: 800; height: 1.25rem; justify-content: center; width: 1.25rem; }
  [data-tone='success'] .indicator { background: #e8f3eb; color: #28733d; }
  [data-tone='warning'] .indicator { background: #fff3d6; color: #8a5b00; }
  [data-tone='danger'] .indicator { background: #fbe9e7; color: #a33a30; }
  .detail dt { margin-bottom: 0.4rem; }
  .detail dd { color: #4f4d48; }
  dd :global(a), dd :global(code) { overflow-wrap: anywhere; word-break: break-word; }
  dd :global(code) { background: #e9e9e7; border-radius: 4px; color: #37352f; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 0.82rem; padding: 0.12rem 0.3rem; white-space: normal; }
  dd :global(p) { margin: 0.35rem 0 0; }
</style>
