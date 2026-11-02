<script lang="ts">
  import Button from '$lib/components/admin/shared/Button.svelte';
  import type { Snippet } from 'svelte';
  import { modalDialog } from './modal-dialog';

  let { title, titleId, descriptionId, close, children }: {
    title: string;
    titleId: string;
    descriptionId: string;
    close: () => void;
    children: Snippet;
  } = $props();
</script>

<dialog aria-labelledby={titleId} aria-describedby={descriptionId} {@attach modalDialog(close, 'mcp-workspace-heading')}>
  <header>
    <h2 id={titleId} tabindex="-1" data-dialog-title>{title}</h2>
    <Button variant="quiet" iconOnly type="button" aria-label="Close" onclick={close}>×</Button>
  </header>
  {@render children()}
</dialog>

<style>
  dialog { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius-panel); box-shadow: var(--admin-shadow-dialog); box-sizing: border-box; color: var(--admin-ink); max-height: calc(100dvh - 2rem); max-width: 36rem; overflow: hidden; padding: 1.5rem; width: calc(100% - 2rem); }
  dialog[open] { display: flex; flex-direction: column; }
  dialog::backdrop { background: var(--admin-overlay); }
  header { align-items: center; border-bottom: 1px solid var(--admin-border); display: flex; flex: none; gap: 1rem; justify-content: space-between; padding-bottom: 1rem; }
  h2 { font-size: 1.25rem; font-weight: 600; letter-spacing: -0.03em; margin: 0; }
  h2:focus-visible { outline: 3px solid var(--admin-focus); outline-offset: 3px; }
  @media (max-width: 30rem) {
    dialog { border-radius: 12px 12px 0 0; margin: auto 0 0; max-height: calc(100dvh - 1rem); max-width: none; padding: 1rem; width: 100%; }
  }
</style>
