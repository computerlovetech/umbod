<script lang="ts">
  type Period = 7 | 30;
  const periods: readonly Period[] = [7, 30];

  let { value, onchange }: { value: Period; onchange: (period: Period) => void } = $props();
</script>

<div class="period-switch" role="group" aria-label="Time period">
  {#each periods as period (period)}
    <button class={value === period ? 'selected' : ''} aria-pressed={value === period} onclick={() => onchange(period)}>{period} days</button>
  {/each}
</div>

<style>
  .period-switch { display: inline-flex; align-items: center; flex-shrink: 0; background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: 6px; padding: 2px; }
  button { border: 0; border-radius: 4px; background: transparent; color: var(--admin-muted); padding: 8px 12px; font: inherit; font-size: 13px; line-height: 1.4; white-space: nowrap; cursor: pointer; }
  button.selected { background: var(--admin-panel); color: var(--admin-ink); box-shadow: 0 1px 3px rgb(20 32 28 / 8%); }
</style>
