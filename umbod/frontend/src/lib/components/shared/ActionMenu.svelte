<script lang="ts">
  import { tick, type Snippet } from 'svelte';
  import { ActionMenuState } from './action-menu-state.svelte';

  type Props = {
    open: boolean;
    disabled?: boolean;
    appearance?: 'icon' | 'surface';
    align?: 'start' | 'end';
    label: string;
    menu: Snippet;
    trigger: Snippet;
    onopenchange: (open: boolean) => void;
  };

  let { open, label, menu, trigger, onopenchange, disabled = false, appearance = 'icon', align = 'start' }: Props = $props();
  const generatedId = $props.id();
  const menuId = `action-menu-${generatedId}`;
  const state = new ActionMenuState(() => align);

  function toggle(): void {
    if (disabled) return;
    const nextOpen = !open;
    onopenchange(nextOpen);
    if (nextOpen) void tick().then(() => state.focusItem('first'));
  }

  function handleTriggerKeydown(event: KeyboardEvent): void {
    if (!disabled) state.triggerKeydown(event, onopenchange);
  }

  function handleMenuKeydown(event: KeyboardEvent): void {
    if (!disabled) state.menuKeydown(event, onopenchange);
  }

  function handleDocumentClick(event: MouseEvent): void {
    state.outsideClick(event, open, onopenchange);
  }
</script>

<svelte:document onclick={handleDocumentClick} />
<svelte:window onresize={state.positionMenu} onscroll={state.positionMenu} />

<div class="action-menu">
  <button
    bind:this={state.trigger}
    class={["trigger", appearance === "surface" && "surface"]}
    type="button"
    aria-label={label}
    aria-haspopup="menu"
    {disabled}
    aria-expanded={open && !disabled}
    aria-controls={menuId}
    onclick={toggle}
    onkeydown={handleTriggerKeydown}
  >{@render trigger()}</button>
  {#if open && !disabled}
    <div id={menuId} {@attach state.attachMenu} class="popup" role="menu" tabindex="-1" aria-label={label} onkeydown={handleMenuKeydown}>
      {@render menu()}
    </div>
  {/if}
</div>

<style>
  .action-menu { position: relative; flex: 0 0 auto; }
  .trigger { position: relative; z-index: var(--action-menu-trigger-z-index, auto); align-items: center; background: transparent; border: 0; border-radius: 4px; color: var(--admin-muted); cursor: pointer; display: inline-flex; font: inherit; font-size: 1.15rem; height: var(--action-menu-trigger-size, 2rem); justify-content: center; padding: 0; width: var(--action-menu-trigger-size, 2rem); }
  .trigger.surface { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); color: var(--admin-ink); font-size: inherit; height: auto; justify-content: flex-start; padding: 7px 8px; text-align: left; width: 100%; }
  .trigger.surface:hover:not(:disabled), .trigger.surface[aria-expanded='true'] { background: var(--admin-accent-soft); color: var(--admin-ink); }
  .trigger:disabled { cursor: not-allowed; opacity: 0.5; }
  .trigger:hover:not(:disabled) { background: var(--admin-border); color: var(--admin-ink); }
  .trigger:focus-visible, .popup :global([role='menuitem']:focus-visible), .popup :global(button:focus-visible) { outline: 2px solid var(--admin-accent); outline-offset: 2px; }
  .popup { box-sizing: border-box; background: var(--admin-panel); border: 1px solid var(--admin-border-strong); border-radius: 7px; box-shadow: var(--admin-shadow); min-width: min(var(--action-menu-min-width, 10rem), calc(100vw - 2rem)); max-width: min(22rem, calc(100vw - 2rem)); max-height: 60vh; overflow: auto; overflow-wrap: anywhere; padding: 0.3rem; position: fixed; z-index: 20; }
  .popup :global([role='menuitem']), .popup :global(button) { background: transparent; border: 0; border-radius: 4px; color: var(--admin-ink); cursor: pointer; display: block; font: inherit; font-size: 0.84rem; padding: 0.5rem 0.6rem; text-align: left; width: 100%; box-sizing: border-box; text-decoration: none; }
  .popup :global([role='menuitem']:hover), .popup :global(button:hover) { background: var(--admin-soft); }
  .popup :global([disabled]), .popup :global([aria-disabled='true']) { cursor: not-allowed; opacity: 0.5; }
  .popup :global(form) { margin: 0; }
</style>
