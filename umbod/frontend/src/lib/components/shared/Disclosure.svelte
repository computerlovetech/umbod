<script lang="ts">
  import Button from '#lib/components/admin/shared/Button.svelte';
  import { untrack, type Snippet } from 'svelte';
  import { DisclosureState } from './disclosure-state.svelte';

  let { label, children, accessibleName, initiallyOpen = false, expanded, onOpenChange }: {
    label: Snippet<[boolean]>;
    children: Snippet<[() => void]>;
    accessibleName?: string;
    initiallyOpen?: boolean;
    expanded?: boolean;
    onOpenChange?: (open: boolean) => void;
  } = $props();

  const id = $props.id();
  const panelId = `${id}-panel`;
  const state = new DisclosureState(untrack(() => initiallyOpen), () => expanded, (open): void => onOpenChange?.(open));

  $effect.pre((): void => {
    if (expanded === false) state.restoreFocus();
  });

  export function open(): void {
    state.open();
  }

  export function close(): void {
    state.close();
  }
</script>

<Button variant="unstyled" class="disclosure-trigger" type="button" aria-label={accessibleName} aria-expanded={state.expanded} aria-controls={panelId} onclick={state.toggle} {@attach state.attachTrigger}>
  {@render label(state.expanded)}
  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 10 5 5 5-5" /></svg>
</Button>
<div id={panelId} class="disclosure-panel" hidden={!state.expanded} inert={!state.expanded} {@attach state.attachPanel}>
  <div class="disclosure-content">
    {@render children(state.close)}
  </div>
</div>

<style>
  :global(button.disclosure-trigger) {
    align-items: center;
    background: transparent;
    border: 0;
    border-radius: var(--disclosure-trigger-radius, 4px);
    box-sizing: border-box;
    color: inherit;
    cursor: pointer;
    display: flex;
    font: inherit;
    gap: var(--disclosure-trigger-gap, 0.5rem);
    justify-content: space-between;
    min-height: var(--disclosure-trigger-min-height, 24px);
    padding: var(--disclosure-trigger-padding, 0);
    text-align: start;
    width: var(--disclosure-trigger-width, 100%);
  }
  :global(button.disclosure-trigger:hover) { color: var(--disclosure-trigger-hover-color, inherit); }
  :global(button.disclosure-trigger[aria-expanded='true']) { background: var(--disclosure-expanded-background, transparent); }
  :global(button.disclosure-trigger:hover) { background: var(--disclosure-trigger-hover-background, var(--disclosure-expanded-background, transparent)); }
  :global(button.disclosure-trigger[aria-expanded='false']:hover) { background: var(--disclosure-trigger-hover-background, transparent); }
  :global(button.disclosure-trigger:focus-visible) { outline: 3px solid var(--admin-focus); outline-offset: 2px; }
  svg { color: var(--admin-muted); flex: none; width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
  :global(button.disclosure-trigger[aria-expanded='true']) > svg { transform: rotate(180deg); }
  .disclosure-panel[hidden] { display: none; }

  @media (prefers-reduced-motion: no-preference) {
    svg { transition: transform 160ms ease; }

    @supports (transition-behavior: allow-discrete) {
      .disclosure-panel {
        --disclosure-motion-duration: 160ms;
        display: grid;
        grid-template-rows: 1fr;
        transition: grid-template-rows var(--disclosure-motion-duration) ease, display var(--disclosure-motion-duration) allow-discrete;
      }

      .disclosure-panel[hidden] { grid-template-rows: 0fr; }

      .disclosure-content {
        min-block-size: 0;
        min-inline-size: 0;
        transition: overflow 0s var(--disclosure-motion-duration) allow-discrete;
      }

      .disclosure-panel[hidden] > .disclosure-content { overflow: clip; transition-delay: 0s; }

      @starting-style {
        .disclosure-panel:not([hidden]) { grid-template-rows: 0fr; }
        .disclosure-panel:not([hidden]) > .disclosure-content { overflow: clip; }
      }
    }
  }
</style>
