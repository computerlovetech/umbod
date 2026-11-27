<script lang="ts">
  import Button from '#lib/components/admin/shared/Button.svelte';
  import type { ActivityChart } from './types';
  import { ActivityTooltip } from './activity-tooltip.svelte';
  import './visualizations.css';
  let { data }: { data: ActivityChart } = $props();
  const tooltipId = $props.id();
  const tooltip = new ActivityTooltip(() => data);
</script>

<div class="dv-chart-legend"><span><i class="dv-success"></i>Successful</span><span><i class="dv-failure"></i>Failed</span><span><i class="dv-cancelled"></i>Cancelled</span></div>
<svelte:window onkeydown={tooltip.dismiss} />

<div class="dv-plot" role="group" aria-label={data.label} onpointerleave={tooltip.leave}>
  <div class="dv-y-axis"><span>{data.axisMaximum}</span><span>{data.axisMaximum / 2}</span><span>0</span></div>
  <div class="dv-plot-body">
    <div class="dv-grid-line dv-top"></div><div class="dv-grid-line dv-middle"></div><div class="dv-grid-line dv-bottom"></div>
    <div class="dv-bars">
      {#if data.total > 0}
      {#each data.days as day (day.date)}
        <Button variant="unstyled"
          type="button"
          class={['dv-bar-column', 'dv-day-trigger', { 'dv-day-active': tooltip.day?.date === day.date }]}
          aria-label={`${day.date}: ${day.total} tool calls`}
          aria-describedby={tooltip.day?.date === day.date ? tooltipId : undefined}
          onpointerenter={() => tooltip.hover(day.date)}
          onfocus={() => tooltip.focus(day.date)}
          onblur={tooltip.blur}
          onclick={() => tooltip.focus(day.date)}
        >
          <span class="dv-bar" role="img" aria-label={`${day.date}: ${day.success} successful, ${day.failure} failed, ${day.cancelled} cancelled tool calls`}>
            <span class="dv-cancelled" style:--segment={`${day.cancelled / data.axisMaximum * 100}%`}></span>
            <span class="dv-failure" style:--segment={`${day.failure / data.axisMaximum * 100}%`}></span>
            <span class="dv-success" style:--segment={`${day.success / data.axisMaximum * 100}%`}></span>
          </span>
        </Button>
      {/each}
      {/if}
    </div>
    {#if tooltip.day}
      <div class="dv-activity-tooltip" id={tooltipId} role="tooltip" style:--day-position={`${tooltip.position}%`}>
        <div class="dv-tooltip-heading"><strong>{tooltip.day.label}, {tooltip.day.date.slice(0, 4)}</strong><span>UTC</span></div>
        <dl class="dv-tooltip-values">
          <div><dt><i class="dv-success"></i>Successful</dt><dd>{tooltip.day.success}</dd></div>
          <div><dt><i class="dv-failure"></i>Failed</dt><dd>{tooltip.day.failure}</dd></div>
          <div><dt><i class="dv-cancelled"></i>Cancelled</dt><dd>{tooltip.day.cancelled}</dd></div>
        </dl>
        <div class="dv-tooltip-total"><span>Total calls</span><strong>{tooltip.day.total}</strong></div>
      </div>
    {/if}
  </div>
</div>
<div class="dv-x-axis"><span>{data.days[0]?.label ?? ''}</span><span>{data.days[Math.floor(data.days.length / 2)]?.label ?? ''}</span><span>{data.days[data.days.length - 1]?.label ?? ''}</span></div>
<div class="dv-activity-footer"><span>Daily calls</span><span>UTC</span></div>
