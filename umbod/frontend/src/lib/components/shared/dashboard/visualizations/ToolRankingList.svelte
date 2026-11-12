<script lang="ts">
  import type { RankedTool } from './types';
  import EmptyToolRanking from './EmptyToolRanking.svelte';
  import './visualizations.css';
  let { tools }: { tools: readonly RankedTool[] } = $props();
</script>

{#if tools.length > 0}
  <ol class="tool-ranking" aria-label="Top tools by call count">
    {#each tools as tool, index (tool.id)}
      <li>
        <span class="dv-rank" aria-hidden="true">{index + 1}</span>
        <div class="dv-ranked-tool">
          <div class="dv-tool-identity"><span class="dv-tool-name">{tool.name}</span><span class="dv-tool-connector">{tool.connector}</span></div>
          <div class="dv-rank-track" aria-hidden="true"><div style:--width={`${tool.barWidth}%`}></div></div>
        </div>
        <span class="dv-tool-count">{tool.count.toLocaleString('en')} calls</span>
      </li>
    {/each}
  </ol>
{:else}
  <EmptyToolRanking />
{/if}
