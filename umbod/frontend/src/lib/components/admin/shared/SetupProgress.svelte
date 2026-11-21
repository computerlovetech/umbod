<script lang="ts">
  let { steps, current }: { steps: readonly string[]; current: number } = $props();
</script>

<ol aria-label="Setup progress" style:--step-count={steps.length}>
  {#each steps as label, index (label)}
    <li aria-current={current === index + 1 ? 'step' : undefined} class={current > index + 1 ? 'complete' : undefined}>
      <span aria-hidden="true">{current > index + 1 ? '✓' : index + 1}</span>
      <span class="label">{label}</span>
    </li>
  {/each}
</ol>

<style>
  ol { display: grid; grid-template-columns: repeat(var(--step-count), minmax(0, 1fr)); gap: .5rem; list-style: none; padding: 0 0 1rem; margin: 1.125rem 0; border-bottom: 1px solid var(--admin-border); color: var(--admin-muted); }
  li { display: flex; align-items: center; gap: .45rem; font-size: .8125rem; }
  [aria-current='step'], .complete { color: var(--admin-accent); font-weight: 700; }
  span[aria-hidden] { display: grid; place-items: center; width: 1.55rem; height: 1.55rem; flex: 0 0 auto; border-radius: 50%; background: var(--admin-soft); border: 1px solid var(--admin-border); font-size: .75rem; font-weight: 650; }
  [aria-current='step'] span[aria-hidden] { background: var(--admin-accent); border-color: var(--admin-accent); color: white; }
  .complete span[aria-hidden] { background: var(--admin-accent-soft); border-color: var(--admin-accent-border); }
  .label { overflow-wrap: anywhere; }
  @media (max-width: 30rem) { li { flex-direction: column; align-items: flex-start; gap: .25rem; font-size: .75rem; } }
</style>
