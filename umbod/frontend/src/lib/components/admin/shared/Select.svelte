<script lang="ts">
  import { untrack } from 'svelte';
  import { calculateSelectOverlayGeometry, SelectState, type SelectOption } from './select-state.svelte';

  let { options, label, value, onchange, disabled = false, compact = false, id, name, accessibleName }: {
    options: SelectOption[]; label: string; value: string; onchange: (value: string) => void; disabled?: boolean; compact?: boolean; id?: string; name?: string; accessibleName?: string;
  } = $props();

  const generatedId = $props.id();
  const selectId = $derived(id ?? `select-${generatedId}`);
  const listboxId = $derived(`${selectId}-listbox`);
  const state = new SelectState(untrack(() => options), untrack(() => value));
  let triggerElement: HTMLButtonElement;

  function choose(optionValue: string): void {
    const selectedValue = state.select(optionValue);
    if (selectedValue !== undefined) {
      onchange(selectedValue);
      triggerElement.focus();
    }
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (disabled) return;
    if (event.key === 'Tab') {
      state.close();
      return;
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      if (!state.isOpen) state.open();
      else if (state.activeValue !== undefined) choose(state.activeValue);
      return;
    }
    if (event.key === 'Escape' && state.isOpen) {
      event.preventDefault();
      state.close();
      triggerElement.focus();
      return;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Home' || event.key === 'End') {
      event.preventDefault();
      if (!state.isOpen) state.open();
      if (event.key === 'ArrowDown') state.moveNext();
      if (event.key === 'ArrowUp') state.movePrevious();
      if (event.key === 'Home') state.moveFirst();
      if (event.key === 'End') state.moveLast();
    }
  }

  function overlay(node: HTMLUListElement): () => void {
    document.body.append(node);
    let animationFrame = 0;
    const position = (): void => {
      animationFrame = 0;
      const visualViewport = window.visualViewport;
      state.setOverlayGeometry(calculateSelectOverlayGeometry(triggerElement.getBoundingClientRect(), {
        width: visualViewport?.width ?? window.innerWidth,
        height: visualViewport?.height ?? window.innerHeight,
        offsetLeft: visualViewport?.offsetLeft ?? 0,
        offsetTop: visualViewport?.offsetTop ?? 0
      }, node.scrollHeight));
    };
    const schedulePosition = (): void => {
      if (!animationFrame) animationFrame = requestAnimationFrame(position);
    };
    const closeOutside = (event: PointerEvent): void => {
      const target = event.target;
      if (target instanceof Node && !node.contains(target) && !triggerElement.contains(target)) state.close();
    };
    position();
    window.addEventListener('scroll', schedulePosition, true);
    window.addEventListener('resize', schedulePosition);
    window.visualViewport?.addEventListener('resize', schedulePosition);
    window.visualViewport?.addEventListener('scroll', schedulePosition);
    document.addEventListener('pointerdown', closeOutside, true);
    return () => {
      cancelAnimationFrame(animationFrame);
      window.removeEventListener('scroll', schedulePosition, true);
      window.removeEventListener('resize', schedulePosition);
      window.visualViewport?.removeEventListener('resize', schedulePosition);
      window.visualViewport?.removeEventListener('scroll', schedulePosition);
      document.removeEventListener('pointerdown', closeOutside, true);
    };
  }
</script>

<div class={['select', { compact }]}>
  <label for={selectId}>{label}</label>
  <button bind:this={triggerElement} type="button" {disabled} id={selectId} class="trigger" role="combobox" aria-label={accessibleName} aria-haspopup="listbox" aria-expanded={state.isOpen} aria-controls={listboxId} aria-activedescendant={state.isOpen && state.activeValue !== undefined ? `${selectId}-option-${state.activeValue}` : undefined} value={state.selectedValue} onclick={state.toggle} onkeydown={handleKeydown}>
    <span>{state.selectedOption?.label ?? state.selectedValue}</span><span class="chevron" aria-hidden="true">⌄</span>
  </button>
  {#if name}<input type="hidden" {name} value={state.selectedValue} disabled={disabled} />{/if}
</div>

{#if state.isOpen}
  <ul {@attach overlay} id={listboxId} class={['listbox', { compact }]} role="listbox" aria-label={accessibleName ?? label} style:left={`${state.overlayGeometry?.left ?? 0}px`} style:top={`${state.overlayGeometry?.top ?? 0}px`} style:width={`${state.overlayGeometry?.width ?? 0}px`} style:max-height={`${state.overlayGeometry?.maxHeight ?? 0}px`} style:visibility={state.overlayGeometry ? 'visible' : 'hidden'}>
    {#each options as option (option.value)}
      <li id={`${selectId}-option-${option.value}`} role="option" aria-selected={option.value === state.selectedValue} aria-disabled={option.disabled || undefined} class={['option', { active: option.value === state.activeValue, disabled: option.disabled }]} onclick={() => choose(option.value)} onkeydown={(event) => { if (event.key === 'Enter' || event.key === ' ') choose(option.value); }} onmousemove={() => state.setActive(option.value)}>
        <span>{option.label}</span>{#if option.value === state.selectedValue}<span class="check" aria-hidden="true">✓</span>{/if}
      </li>
    {/each}
  </ul>
{/if}

<style>
  .select { display: grid; gap: 0.35rem; min-width: 0; }
  label { font-size: 0.8125rem; font-weight: 600; }
  .trigger { align-items: center; background: #fff; border: 1px solid #e9e9e7; border-radius: 6px; color: #37352f; display: flex; font: inherit; justify-content: space-between; min-height: 2.75rem; padding: 0.65rem 0.7rem; text-align: left; width: 100%; }
  .select.compact { gap: 0.25rem; }
  .select.compact label { font-size: 0.75rem; }
  .select.compact .trigger { font-size: 0.875rem; min-height: 2.25rem; padding: 0.45rem 0.6rem; }
  .trigger:not(:disabled) { cursor: pointer; }
  .trigger:focus-visible { border-color: #2f6feb; outline: 3px solid rgb(47 111 235 / 24%); outline-offset: 2px; }
  .trigger:disabled { background: #f1f1ef; color: #8f8e8a; cursor: not-allowed; }
  .chevron { color: #787774; font-size: 1rem; margin-left: 0.75rem; }
  .listbox { background: #fff; border: 1px solid #d7d7d4; border-radius: 8px; box-shadow: 0 8px 24px rgb(15 15 15 / 14%); box-sizing: border-box; color: #37352f; list-style: none; margin: 0; overflow-y: auto; padding: 0.25rem; position: fixed; z-index: 1000; }
  .option { align-items: center; border-radius: 5px; cursor: pointer; display: flex; gap: 0.75rem; justify-content: space-between; min-height: 2.25rem; padding: 0.4rem 0.55rem; white-space: nowrap; }
  .listbox.compact .option { font-size: 0.875rem; }
  .option.active { background: #f1f1ef; }
  .option.disabled { color: #8f8e8a; cursor: not-allowed; }
  .check { color: #2f6feb; font-weight: 700; }
</style>
