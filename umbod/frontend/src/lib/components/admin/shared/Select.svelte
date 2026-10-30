<script lang="ts">
  import { tick } from 'svelte';
  import { calculateSelectOverlayGeometry, SelectState, type SelectOption } from './select-state.svelte';

  let { options, label, value, onchange, disabled = false, compact = false, id, name, accessibleName, search, emptyMessage = 'No options found' }: {
    options: SelectOption[]; label: string; value: string; onchange: (value: string) => void; disabled?: boolean; compact?: boolean; id?: string; name?: string; accessibleName?: string;
    search?: { value: string; oninput: (value: string) => void; placeholder: string }; emptyMessage?: string;
  } = $props();

  const generatedId = $props.id();
  const selectId = $derived(id ?? `select-${generatedId}`);
  const listboxId = $derived(`${selectId}-listbox`);
  const state = new SelectState(() => options, () => value);
  let triggerElement: HTMLElement;

  function attachTrigger(node: HTMLElement): () => void {
    triggerElement = node;
    node.addEventListener('keydown', handleKeydown);
    return () => node.removeEventListener('keydown', handleKeydown);
  }

  function unavailable(): boolean {
    return disabled || triggerElement?.matches(':disabled') || Boolean(triggerElement?.closest('fieldset[disabled]'));
  }

  function optionId(optionValue: string): string {
    return `${selectId}-option-${encodeURIComponent(optionValue)}`;
  }

  function open(): void {
    if (!unavailable()) state.open();
  }

  function handleInput(event: Event): void {
    if (unavailable()) return;
    search?.oninput((event.currentTarget as HTMLInputElement).value);
    open();
  }

  function scrollActive(node: HTMLLIElement): void {
    if (node.id === optionId(state.activeValue ?? '')) node.scrollIntoView?.({ block: 'nearest' });
  }

  async function choose(optionValue: string): Promise<void> {
    if (unavailable()) return;
    const selectedValue = state.select(optionValue);
    if (selectedValue !== undefined) {
      onchange(selectedValue);
      await tick();
      if (triggerElement?.isConnected) triggerElement.focus();
      state.close();
    }
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (unavailable()) return;
    if (event.key === 'Tab') {
      state.close();
      return;
    }
    if (event.key === 'Enter' || (!search && event.key === ' ')) {
      event.preventDefault();
      if (!state.isOpen) state.open();
      else if (state.activeValue !== undefined) choose(state.activeValue);
      return;
    }
    if (event.key === 'Escape' && state.isOpen) {
      event.preventDefault();
      event.stopPropagation();
      if (triggerElement?.isConnected) triggerElement.focus();
      state.close();
      return;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp' || (!search && (event.key === 'Home' || event.key === 'End'))) {
      event.preventDefault();
      const wasOpen = state.isOpen;
      if (!wasOpen) state.open();
      if (event.key === 'ArrowDown' && wasOpen) state.moveNext();
      if (event.key === 'ArrowUp') {
        if (wasOpen) state.movePrevious();
        else state.moveLast();
      }
      if (event.key === 'Home') state.moveFirst();
      if (event.key === 'End') state.moveLast();
    }
  }

  function overlay(node: HTMLUListElement): () => void {
    (triggerElement.closest('dialog') ?? document.body).append(node);
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
    const resizeObserver = new ResizeObserver(schedulePosition);
    const mutationObserver = new MutationObserver(schedulePosition);
    resizeObserver.observe(node);
    resizeObserver.observe(triggerElement);
    mutationObserver.observe(node, { childList: true, subtree: true, characterData: true });
    position();
    window.addEventListener('scroll', schedulePosition, true);
    window.addEventListener('resize', schedulePosition);
    window.visualViewport?.addEventListener('resize', schedulePosition);
    window.visualViewport?.addEventListener('scroll', schedulePosition);
    document.addEventListener('pointerdown', closeOutside, true);
    return () => {
      resizeObserver.disconnect();
      mutationObserver.disconnect();
      cancelAnimationFrame(animationFrame);
      window.removeEventListener('scroll', schedulePosition, true);
      window.removeEventListener('resize', schedulePosition);
      window.visualViewport?.removeEventListener('resize', schedulePosition);
      window.visualViewport?.removeEventListener('scroll', schedulePosition);
      document.removeEventListener('pointerdown', closeOutside, true);
      node.remove();
    };
  }
</script>

<div class={['select', { compact }]}>
  <label for={selectId}>{label}</label>
  {#if search}
    <input {@attach attachTrigger} type="text" {disabled} id={selectId} class="trigger searchable" role="combobox" aria-label={accessibleName} aria-autocomplete="list" aria-haspopup="listbox" aria-expanded={state.isOpen && !disabled} aria-controls={listboxId} aria-activedescendant={state.isOpen && !disabled && state.activeValue !== undefined ? optionId(state.activeValue) : undefined} value={search.value} placeholder={search.placeholder} oninput={handleInput} onfocus={open} onclick={open} onblur={state.close} />
  {:else}
  <button {@attach attachTrigger} type="button" {disabled} id={selectId} class="trigger" role="combobox" aria-label={accessibleName} aria-haspopup="listbox" aria-expanded={state.isOpen && !disabled} aria-controls={listboxId} aria-activedescendant={state.isOpen && !disabled && state.activeValue !== undefined ? optionId(state.activeValue) : undefined} value={state.selectedValue} onclick={() => { if (!unavailable()) state.toggle(); }} onblur={state.close}>
    <span>{state.selectedOption?.label ?? state.selectedValue}</span><span class="chevron" aria-hidden="true">⌄</span>
  </button>
  {/if}
  {#if name}<input type="hidden" {name} value={state.selectedValue} disabled={disabled} />{/if}
</div>

{#if state.isOpen && !disabled}
  <ul {@attach overlay} id={listboxId} class={['listbox', { compact }]} role="listbox" aria-label={accessibleName ?? label} style:left={`${state.overlayGeometry?.left ?? 0}px`} style:top={`${state.overlayGeometry?.top ?? 0}px`} style:width={`${state.overlayGeometry?.width ?? 0}px`} style:max-height={`${state.overlayGeometry?.maxHeight ?? 0}px`} style:visibility={state.overlayGeometry ? 'visible' : 'hidden'}>
    {#each options as option (option.value)}
      <li {@attach scrollActive} id={optionId(option.value)} role="option" aria-selected={option.value === state.selectedValue} aria-disabled={option.disabled || undefined} class={['option', { active: option.value === state.activeValue, disabled: option.disabled }]} onpointerdown={(event) => event.preventDefault()} onclick={() => choose(option.value)} onkeydown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(option.value); } }} onmousemove={() => { if (!unavailable()) state.setActive(option.value); }}>
        <span>{option.label}</span>{#if option.value === state.selectedValue}<span class="check" aria-hidden="true">✓</span>{/if}
      </li>
    {:else}
      <li role="presentation" class="empty"><span role="status" aria-live="polite">{emptyMessage}</span></li>
    {/each}
  </ul>
{/if}

<style>
  .select { display: grid; gap: 0.35rem; min-width: 0; }
  label { font-size: 0.8125rem; font-weight: 600; }
  .trigger { align-items: center; background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: 6px; color: var(--admin-ink); display: flex; font: inherit; justify-content: space-between; min-height: 2.75rem; padding: 0.65rem 0.7rem; text-align: left; width: 100%; }
  .select.compact { gap: 0.25rem; }
  .select.compact label { font-size: 0.75rem; }
  .select.compact .trigger { font-size: 0.875rem; min-height: 2.25rem; padding: 0.45rem 0.6rem; }
  .trigger:not(:disabled) { cursor: pointer; }
  .trigger:focus-visible { border-color: var(--admin-accent); outline: 3px solid var(--admin-focus); outline-offset: 2px; }
  .trigger:disabled { background: var(--admin-soft); color: var(--admin-muted); cursor: not-allowed; }
  .trigger.searchable { box-sizing: border-box; cursor: text; }
  .empty { color: var(--admin-muted); padding: 0.65rem 0.55rem; }
  .chevron { color: var(--admin-muted); font-size: 1rem; margin-left: 0.75rem; }
  .listbox { background: var(--admin-panel); border: 1px solid var(--admin-border-strong); border-radius: 8px; box-shadow: var(--admin-shadow); box-sizing: border-box; color: var(--admin-ink); list-style: none; margin: 0; overflow-y: auto; padding: 0.25rem; position: fixed; z-index: 1000; }
  .option { align-items: center; border-radius: 5px; cursor: pointer; display: flex; gap: 0.75rem; justify-content: space-between; min-height: 2.25rem; padding: 0.4rem 0.55rem; white-space: normal; overflow-wrap: anywhere; }
  .option > span:first-child { min-width: 0; }
  .listbox.compact .option { font-size: 0.875rem; }
  .option.active { background: var(--admin-soft); }
  .option.disabled { color: var(--admin-muted); cursor: not-allowed; }
  .check { color: var(--admin-accent); font-weight: 700; }
</style>
