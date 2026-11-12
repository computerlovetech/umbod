<script lang="ts">
  const ranks: readonly number[] = [1, 2, 3, 4, 5];
</script>

<div class="empty-ranking" role="img" aria-label="No per-tool usage data">
  <div aria-hidden="true">
    {#each ranks as rank (rank)}
      <div class="empty-ranking-row">
        <span class="rank">{rank}</span>
        <div class="tool-shape">
          <div class="identity-shape"><span class="name-shape"></span><span class="connector-shape"></span></div>
          <div class="bar-track"></div>
        </div>
        <span class="count-shape"></span>
      </div>
    {/each}
  </div>
</div>

<style>
  .empty-ranking-row { display: flex; align-items: center; gap: 12px; padding: 15px 0; }
  .empty-ranking-row + .empty-ranking-row { border-top: 1px solid var(--admin-soft); }
  .rank { min-width: 10px; font-size: 12px; color: var(--admin-muted); }
  .tool-shape { flex: 1; min-width: 0; }
  .identity-shape { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 8px; min-height: 18px; }
  .name-shape, .connector-shape, .count-shape { display: block; height: 8px; background: var(--admin-soft); border-radius: 2px; }
  .name-shape { width: 48%; max-width: 120px; }
  .connector-shape { width: 22%; max-width: 54px; height: 6px; }
  .count-shape { width: 46px; flex-shrink: 0; }
  .bar-track { height: 4px; background: var(--admin-soft); border-radius: 2px; }
</style>
