<script lang="ts">
  import type { OperationChart } from './types';
  import './visualizations.css';
  let { data }: { data: OperationChart } = $props();
</script>

<div class="dv-mix-bar" role="img" aria-label={data.label}>
  {#each data.segments as item (item.key)}
    <div class={`dv-${item.key}`} style:--share={`${item.share}%`}></div>
  {/each}
</div>
<dl class="dv-mix-legend">
  {#each data.segments as item (item.key)}
    <div><dt><i class={`dv-${item.key}`}></i>{item.label}</dt><dd>{#if data.total > 0}{item.share.toFixed(1)}%{/if}</dd><dd class="dv-muted">{#if data.total > 0}{item.count.toLocaleString('en')}{/if}</dd></div>
  {/each}
</dl>
