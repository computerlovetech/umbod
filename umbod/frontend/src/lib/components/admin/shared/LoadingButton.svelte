<script lang="ts">
  import type { HTMLButtonAttributes, MouseEventHandler } from 'svelte/elements';
  import Button from './Button.svelte';
  import DelayedSpinner from './DelayedSpinner.svelte';
  import { DelayedLoadingState } from './delayed-loading-state.svelte';

  let {
    loading,
    delayMs,
    disabled = false,
    type = 'button',
    label,
    loadingLabel = 'Loading',
    variant = 'primary',
    onclick,
    formaction,
    role,
    title
  }: {
    loading: boolean;
    delayMs?: number;
    disabled?: boolean;
    type?: 'button' | 'submit';
    label: string;
    loadingLabel?: string;
    variant?: 'primary' | 'secondary';
    onclick?: MouseEventHandler<HTMLButtonElement>;
    formaction?: string;
    role?: HTMLButtonAttributes['role'];
    title?: string;
  } = $props();

  const state = new DelayedLoadingState();
  const buttonLabel = $derived(state.visible ? loadingLabel : label);

  $effect(() => {
    if (loading) state.start(delayMs);
    else state.stop();
    return state.stop;
  });
</script>

<Button {variant} {type} {formaction} {role} {title} disabled={disabled || loading} {onclick} aria-busy={loading} aria-label={buttonLabel} class="loading-button">
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
  .loading-button__loading :global(.delayed-spinner__mark) { border-color: rgb(120 119 116 / 35%); border-top-color: currentColor; }
</style>
