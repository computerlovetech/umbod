<script lang="ts">
  import { DelayedLoadingState } from './delayed-loading-state.svelte';

  let {
    active,
    delayMs,
    label = 'Loading',
    size = 'medium',
    inline = false
  }: {
    active: boolean;
    delayMs?: number;
    label?: string;
    size?: 'small' | 'medium';
    inline?: boolean;
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

{#if state.visible}
  <span class={["delayed-spinner", `delayed-spinner--${size}`, inline && 'delayed-spinner--inline']} role="status" aria-live="polite">
    <span class="delayed-spinner__mark" aria-hidden="true"></span>
    <span class="delayed-spinner__label">{label}</span>
  </span>
{/if}

<style>
  .delayed-spinner {
    align-items: center;
    color: #787774;
    display: flex;
    font-size: 13px;
    font-weight: 500;
    gap: 8px;
    justify-content: center;
    line-height: 1.2;
  }

  .delayed-spinner--inline {
    display: inline-flex;
    justify-content: flex-start;
    vertical-align: middle;
  }

  .delayed-spinner__mark {
    animation: delayed-spinner-rotate 0.75s linear infinite;
    border: 2px solid #e9e9e7;
    border-top-color: #37352f;
    border-radius: 50%;
    box-sizing: border-box;
    flex: 0 0 auto;
  }

  .delayed-spinner--small .delayed-spinner__mark {
    height: 14px;
    width: 14px;
  }

  .delayed-spinner--medium .delayed-spinner__mark {
    height: 18px;
    width: 18px;
  }

  .delayed-spinner__label {
    color: #787774;
    white-space: nowrap;
  }

  @keyframes delayed-spinner-rotate {
    to {
      transform: rotate(360deg);
    }
  }
</style>
