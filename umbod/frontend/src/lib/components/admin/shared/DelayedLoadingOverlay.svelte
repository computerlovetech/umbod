<script lang="ts">
  import type { Snippet } from 'svelte';
  import DelayedSpinner from './DelayedSpinner.svelte';
  import { DelayedLoadingState } from './delayed-loading-state.svelte';

  let {
    active,
    delayMs,
    label = 'Loading',
    children
  }: {
    active: boolean;
    delayMs?: number;
    label?: string;
    children: Snippet;
  } = $props();

  const state = new DelayedLoadingState();

  $effect(() => {
    if (active) {
      state.start(delayMs);
    } else {
      state.stop();
    }

    return state.stop;
  });
</script>

<div class="delayed-loading-overlay">
  {@render children()}

  {#if state.visible}
    <div class="delayed-loading-overlay__scrim">
      <div class="delayed-loading-overlay__panel">
        <DelayedSpinner active={state.visible} delayMs={0} {label} />
      </div>
    </div>
  {/if}
</div>

<style>
  .delayed-loading-overlay {
    position: relative;
  }

  .delayed-loading-overlay__scrim {
    align-items: center;
    background: rgb(250 250 249 / 72%);
    border-radius: inherit;
    display: flex;
    inset: 0;
    justify-content: center;
    min-height: 100%;
    position: absolute;
    z-index: 1;
  }

  .delayed-loading-overlay__panel {
    background: #ffffff;
    border: 1px solid #e9e9e7;
    border-radius: 8px;
    box-shadow: 0 8px 24px rgb(15 15 15 / 8%);
    color: #37352f;
    padding: 10px 14px;
  }
</style>
