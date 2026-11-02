<script lang="ts">
  import type { ComponentProps } from 'svelte';
  import Button from './Button.svelte';
  import DelayedSpinner from './DelayedSpinner.svelte';
  import { DelayedLoadingState } from './delayed-loading-state.svelte';

  let {
    loading,
    delayMs,
    disabled = false,
    label,
    loadingLabel = 'Loading',
    ref = $bindable(),
    class: className,
    ...attributes
  }: Omit<ComponentProps<typeof Button>, 'children'> & {
    loading: boolean;
    delayMs?: number;
    label: string;
    loadingLabel?: string;
  } = $props();

  const state = new DelayedLoadingState();
  const buttonLabel = $derived(state.visible ? loadingLabel : label);

  $effect(() => {
    if (loading) state.start(delayMs);
    else state.stop();
    return state.stop;
  });
</script>

<Button {...attributes} bind:ref disabled={disabled || loading} aria-busy={loading} aria-label={buttonLabel} class={['loading-button', className]}>
  <span class="loading-button__content" aria-hidden={state.visible}>{label}</span>
  <span class="loading-button__loading" aria-hidden={!state.visible}>
    <DelayedSpinner active={state.visible} delayMs={0} label={loadingLabel} size="small" inline />
  </span>
</Button>

<style>
  :global(.loading-button) {
    display: inline-grid;
    grid-template-areas: 'content';
    position: relative;
  }

  .loading-button__content,
  .loading-button__loading {
    align-items: center;
    display: inline-flex;
    grid-area: content;
    justify-content: center;
  }

  .loading-button__content[aria-hidden='true'],
  .loading-button__loading[aria-hidden='true'] {
    visibility: hidden;
  }

  .loading-button__loading :global(.delayed-spinner__label) { color: currentColor; }
  .loading-button__loading :global(.delayed-spinner__mark) { border-color: var(--admin-border-strong); border-top-color: currentColor; }
</style>
