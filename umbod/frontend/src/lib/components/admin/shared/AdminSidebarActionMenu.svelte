<script lang="ts">
  import type { Snippet } from 'svelte';
  import { AdminSidebarActionMenuState } from './admin-sidebar-action-menu-state.svelte';

  type Props = {
    open: boolean;
    label: string;
    menu: Snippet;
    onopenchange: (open: boolean) => void;
  };

  let { open, label, menu, onopenchange }: Props = $props();
  const generatedId = $props.id();
  const menuId = `admin-sidebar-action-menu-${generatedId}`;
  const state = new AdminSidebarActionMenuState();

  function handleTriggerKeydown(event: KeyboardEvent): void {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
    event.preventDefault();
    onopenchange(true);
    queueMicrotask(() => state.focusItem(event.key === 'ArrowDown' ? 'first' : 'last'));
  }

  function handleMenuKeydown(event: KeyboardEvent): void {
    if (event.key === 'Tab') {
      onopenchange(false);
      return;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      onopenchange(false);
      queueMicrotask(state.restoreTriggerFocus);
      return;
    }
    const direction = event.key === 'ArrowDown' ? 'next' : event.key === 'ArrowUp' ? 'previous' : event.key === 'Home' ? 'first' : event.key === 'End' ? 'last' : null;
    if (direction === null) return;
    event.preventDefault();
    state.focusItem(direction);
  }

  function handleDocumentClick(event: MouseEvent): void {
    if (open && !state.contains(event.target)) onopenchange(false);
  }
</script>

<svelte:document onclick={handleDocumentClick} />

<div class="action-menu">
  <button
    bind:this={state.trigger}
    class="trigger"
    type="button"
    aria-label={label}
    aria-haspopup="menu"
    aria-expanded={open}
    aria-controls={menuId}
    onclick={() => onopenchange(!open)}
    onkeydown={handleTriggerKeydown}
  >⋯</button>
  {#if open}
    <div id={menuId} bind:this={state.menu} class="popup" role="menu" tabindex="-1" aria-label={label} onkeydown={handleMenuKeydown}>
      {@render menu()}
    </div>
  {/if}
</div>

<style>
  .action-menu { position: relative; flex: 0 0 auto; }
  .trigger { align-items: center; background: transparent; border: 0; border-radius: 4px; color: #787774; cursor: pointer; display: inline-flex; font: inherit; font-size: 1.15rem; height: 2rem; justify-content: center; padding: 0; width: 2rem; }
  .trigger:hover { background: #e9e9e7; color: #37352f; }
  .trigger:focus-visible, .popup :global([role='menuitem']:focus-visible), .popup :global(button:focus-visible) { outline: 2px solid #2383e2; outline-offset: 2px; }
  .popup { background: #fff; border: 1px solid #d8d8d4; border-radius: 7px; box-shadow: 0 8px 24px rgb(15 15 15 / 18%); min-width: 10rem; padding: 0.3rem; position: absolute; right: 0; top: calc(100% + 0.25rem); z-index: 20; }
  .popup :global([role='menuitem']), .popup :global(button) { background: transparent; border: 0; border-radius: 4px; color: #37352f; cursor: pointer; display: block; font: inherit; font-size: 0.84rem; padding: 0.5rem 0.6rem; text-align: left; width: 100%; }
  .popup :global([role='menuitem']:hover), .popup :global(button:hover) { background: #f1f1ef; }
  .popup :global([disabled]), .popup :global([aria-disabled='true']) { cursor: not-allowed; opacity: 0.5; }
  .popup :global(form) { margin: 0; }
</style>
