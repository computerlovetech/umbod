<script lang="ts">
  import type { Snippet } from 'svelte';

  let {
    title,
    titleId,
    descriptionId,
    close,
    children
  }: {
    title: string;
    titleId: string;
    descriptionId?: string;
    close: () => void;
    children: Snippet;
  } = $props();

  function handleBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) close();
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') close();
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="backdrop" role="presentation" onclick={handleBackdropClick}>
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={descriptionId}>
    <header>
      <h2 id={titleId}>{title}</h2>
      <button type="button" class="close" aria-label="Close" onclick={close}>×</button>
    </header>
    {@render children()}
  </div>
</div>

<style>
  .backdrop { align-items: center; background: rgb(0 0 0 / 42%); display: flex; inset: 0; justify-content: center; padding: 1rem; position: fixed; z-index: 100; }
  .modal { background: #fff; border-radius: 12px; box-shadow: 0 18px 60px rgb(0 0 0 / 22%); box-sizing: border-box; display: flex; flex-direction: column; max-height: calc(100vh - 2rem); max-width: 34rem; overflow: hidden; padding: 1.25rem; width: 100%; }
  header { align-items: center; display: flex; flex: none; justify-content: space-between; }
  h2 { font-size: 1.2rem; margin: 0; }
  .close { align-items: center; background: transparent; border: 0; border-radius: 6px; cursor: pointer; display: inline-flex; font: inherit; font-size: 1.5rem; height: 2rem; justify-content: center; padding: 0; width: 2rem; }
  .close:hover { background: #f1f1ef; }
  .close:focus-visible { outline: 3px solid rgb(47 111 235 / 24%); outline-offset: 2px; }

  @media (max-width: 30rem) {
    .backdrop { align-items: flex-end; padding: 0; }
    .modal { border-radius: 12px 12px 0 0; max-height: calc(100vh - 1rem); max-width: none; padding: 1rem; }
  }
</style>
