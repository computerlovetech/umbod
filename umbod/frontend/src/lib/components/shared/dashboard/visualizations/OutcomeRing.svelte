<script lang="ts">
  import type { OutcomeChart } from './types';
  import './visualizations.css';
  let { data }: { data: OutcomeChart } = $props();
</script>

<div class="dv-outcomes">
  <svg class="dv-ring" viewBox="0 0 120 120" role="img" aria-label={data.label}>
    <circle cx="60" cy="60" r="48" fill="none" stroke="var(--admin-soft)" stroke-width="9" />
    {#each data.segments as segment (segment.key)}
      <circle class={`dv-${segment.key}`} cx="60" cy="60" r="48" fill="none" stroke-width="9" pathLength="100" stroke-dasharray={`${segment.percentage} ${100 - segment.percentage}`} stroke-dashoffset={-segment.offset} transform="rotate(-90 60 60)" />
    {/each}
    {#if data.total > 0}
      <text x="60" y="60" text-anchor="middle" class="dv-ring-value">{data.successRate}<tspan class="dv-percent">%</tspan></text>
      <text x="60" y="77" text-anchor="middle" class="dv-ring-caption">successful</text>
    {/if}
  </svg>
  <dl class="dv-outcome-legend">
    {#each data.segments as segment (segment.key)}
      <div><dt><i class={`dv-${segment.key}`}></i>{segment.label}</dt><dd>{#if data.total > 0}{segment.percentage.toFixed(1)}%{/if}</dd><dd class="dv-muted">{#if data.total > 0}{segment.count.toLocaleString('en')}{/if}</dd></div>
    {/each}
  </dl>
</div>
