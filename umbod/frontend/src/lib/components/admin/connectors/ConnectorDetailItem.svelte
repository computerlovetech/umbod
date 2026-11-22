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
    <div class="value">{@render children()}</div>
  </dd>
</div>

<style>
  .detail-item { min-width: 0; }
  dt { color: var(--admin-muted); font-size: 0.72rem; font-weight: 650; letter-spacing: 0.04em; margin-bottom: 0.3rem; text-transform: uppercase; }
  dd { color: var(--admin-ink); font-size: 0.9rem; line-height: 1.45; margin: 0; min-width: 0; overflow-wrap: anywhere; }
  .summary dd { align-items: center; display: flex; font-weight: 600; gap: 0.45rem; }
  .indicator { align-items: center; background: var(--admin-soft); border-radius: 50%; color: var(--admin-muted); display: inline-flex; flex: 0 0 auto; font-size: 0.72rem; font-weight: 800; height: 1.25rem; justify-content: center; width: 1.25rem; }
  [data-tone='success'] .indicator { background: var(--admin-success-bg); color: var(--admin-success-text); }
  [data-tone='warning'] .indicator { background: var(--admin-warning-bg); color: var(--admin-warning-text); }
  [data-tone='danger'] .indicator { background: var(--admin-danger-bg); color: var(--admin-danger-text); }
  .value { min-width: 0; }
  .detail { align-items: baseline; display: grid; gap: 0.75rem; grid-template-columns: minmax(8.125rem, 23%) minmax(0, 1fr); padding: 0.45rem 0.75rem; }
  .detail dt { font-size: 0.78rem; letter-spacing: normal; margin: 0; text-transform: none; }
  dd :global(a), dd :global(code) { overflow-wrap: anywhere; }
  dd :global(code) { font-family: var(--admin-mono); font-size: 0.82rem; white-space: normal; }
  @container connector-reference (max-width: 420px) {
    .detail { gap: 0.15rem; grid-template-columns: minmax(0, 1fr); }
  }
  dd :global(p) { margin: 0.35rem 0 0; }
</style>
