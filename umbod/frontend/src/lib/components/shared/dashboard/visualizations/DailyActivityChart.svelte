<script lang="ts">
  import type { ActivityChart } from './types';
  import './visualizations.css';
  let { data }: { data: ActivityChart } = $props();
</script>

<div class="dv-chart-legend"><span><i class="dv-success"></i>Successful</span><span><i class="dv-failure"></i>Failed</span><span><i class="dv-cancelled"></i>Cancelled</span></div>
<div class="dv-plot" role="group" aria-label={data.label}>
  <div class="dv-y-axis"><span>{data.axisMaximum}</span><span>{data.axisMaximum / 2}</span><span>0</span></div>
  <div class="dv-plot-body">
    <div class="dv-grid-line dv-top"></div><div class="dv-grid-line dv-middle"></div><div class="dv-grid-line dv-bottom"></div>
    <div class="dv-bars">
      {#if data.total > 0}
      {#each data.days as day (day.date)}
        <div class="dv-bar-column">
          <div class="dv-bar" role="img" aria-label={`${day.date}: ${day.success} successful, ${day.failure} failed, ${day.cancelled} cancelled tool calls`} title={`${day.label} · ${day.success} successful / ${day.failure} failed / ${day.cancelled} cancelled`}>
            <div class="dv-cancelled" style:--segment={`${day.cancelled / data.axisMaximum * 100}%`}></div>
            <div class="dv-failure" style:--segment={`${day.failure / data.axisMaximum * 100}%`}></div>
            <div class="dv-success" style:--segment={`${day.success / data.axisMaximum * 100}%`}></div>
          </div>
        </div>
      {/each}
      {/if}
    </div>
  </div>
</div>
<div class="dv-x-axis"><span>{data.days[0]?.label ?? ''}</span><span>{data.days[Math.floor(data.days.length / 2)]?.label ?? ''}</span><span>{data.days[data.days.length - 1]?.label ?? ''}</span></div>
<div class="dv-activity-footer"><span>Daily calls</span><span>UTC</span></div>
