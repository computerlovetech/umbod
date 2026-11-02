<script lang="ts">
  import Button from '$lib/components/admin/shared/Button.svelte';
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
      <Button variant="quiet" iconOnly type="button" aria-label="Close" onclick={close}>×</Button>
    </header>
    {@render children()}
  </div>
</div>

<style>
  .backdrop { align-items: center; background: var(--admin-overlay); display: flex; inset: 0; justify-content: center; padding: 1rem; position: fixed; z-index: 100; }
  .modal { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius-panel); box-shadow: var(--admin-shadow-dialog); box-sizing: border-box; color: var(--admin-ink); display: flex; flex-direction: column; max-height: calc(100dvh - 2rem); max-width: 36rem; overflow: hidden; padding: 1.5rem; width: 100%; }
  header { align-items: center; border-bottom: 1px solid var(--admin-border); display: flex; flex: none; gap: 1rem; justify-content: space-between; padding-bottom: 1rem; }
  h2 { font-size: 1.25rem; font-weight: 600; letter-spacing: -0.03em; margin: 0; }

  @media (max-width: 30rem) {
    .backdrop { align-items: flex-end; padding: 0; }
    .modal { border-radius: 12px 12px 0 0; max-height: calc(100dvh - 1rem); max-width: none; padding: 1rem; }
  }
</style>
