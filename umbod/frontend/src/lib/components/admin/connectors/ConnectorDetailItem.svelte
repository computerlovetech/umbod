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
  dt { color: var(--admin-muted); font-size: 0.72rem; font-weight: 650; letter-spacing: 0.04em; margin-bottom: 0.3rem; text-transform: uppercase; }
  dd { color: var(--admin-ink); font-size: 0.9rem; line-height: 1.45; margin: 0; min-width: 0; overflow-wrap: anywhere; }
  .summary dd { align-items: center; display: flex; font-weight: 600; gap: 0.45rem; }
  .indicator { align-items: center; background: var(--admin-soft); border-radius: 50%; color: var(--admin-muted); display: inline-flex; flex: 0 0 auto; font-size: 0.72rem; font-weight: 800; height: 1.25rem; justify-content: center; width: 1.25rem; }
  [data-tone='success'] .indicator { background: var(--admin-success-bg); color: var(--admin-success-text); }
  [data-tone='warning'] .indicator { background: var(--admin-warning-bg); color: var(--admin-warning-text); }
  [data-tone='danger'] .indicator { background: var(--admin-danger-bg); color: var(--admin-danger-text); }
  .detail dt { margin-bottom: 0.4rem; }
  .detail dd { color: var(--admin-ink); }
  dd :global(a), dd :global(code) { overflow-wrap: anywhere; word-break: break-word; }
  dd :global(code) { background: var(--admin-border); border-radius: 4px; color: var(--admin-ink); font-family: var(--admin-mono); font-size: 0.82rem; padding: 0.12rem 0.3rem; white-space: normal; }
  dd :global(p) { margin: 0.35rem 0 0; }
</style>
