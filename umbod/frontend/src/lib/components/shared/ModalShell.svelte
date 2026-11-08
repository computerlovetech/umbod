<script lang="ts">
  import Button from '$lib/components/admin/shared/Button.svelte';
  import type { Snippet } from 'svelte';
  import type { Attachment } from 'svelte/attachments';
  import { nativeDialog } from '$lib/components/shared/dialogs/native-dialog';

  let {
    title,
    titleId,
    descriptionId,
    close,
    closeDisabled = false,
    initialFocus = '[data-dialog-cancel]',
    dialogAttachment,
    role = 'dialog',
    children
  }: {
    title: string;
    titleId: string;
    descriptionId?: string;
    close: () => void;
    closeDisabled?: boolean;
    initialFocus?: string;
    dialogAttachment?: Attachment<HTMLDialogElement>;
    role?: 'dialog' | 'alertdialog';
    children: Snippet;
  } = $props();

  function handleBackdropClick(event: MouseEvent): void {
    if (event.target !== event.currentTarget || closeDisabled) return;
    const bounds = event.currentTarget instanceof HTMLDialogElement ? event.currentTarget.getBoundingClientRect() : null;
    if (bounds && event.clientX >= bounds.left && event.clientX <= bounds.right && event.clientY >= bounds.top && event.clientY <= bounds.bottom) return;
    close();
  }
</script>

<dialog {role} aria-modal="true" aria-labelledby={titleId} aria-describedby={descriptionId} onclick={handleBackdropClick} {@attach dialogAttachment ?? nativeDialog(close, () => !closeDisabled, initialFocus)}>
  <header>
    <h2 id={titleId} tabindex="-1" data-dialog-title>{title}</h2>
    <Button variant="quiet" iconOnly type="button" aria-label="Close" disabled={closeDisabled} onclick={close}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
    </Button>
  </header>
  {@render children()}
</dialog>

<style>
  dialog { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius-panel); box-shadow: var(--admin-shadow-dialog); box-sizing: border-box; color: var(--admin-ink); max-height: calc(100dvh - 2rem); max-width: var(--modal-width, 36rem); overflow: var(--modal-overflow, hidden); padding: var(--modal-padding, 1.5rem); width: calc(100% - 2rem); text-align: start; white-space: normal; }
  dialog[open] { display: flex; flex-direction: column; }
  dialog::backdrop { background: var(--admin-overlay); }
  header { align-items: flex-start; border-bottom: 1px solid var(--admin-border); display: flex; flex: none; gap: 1rem; justify-content: space-between; padding: var(--modal-header-padding, 0 0 1rem); }
  h2 { font-size: 1.25rem; font-weight: 600; letter-spacing: -0.03em; margin: 0; min-width: 0; overflow-wrap: anywhere; }
  svg { display: block; height: 1.25rem; width: 1.25rem; }

  @media (max-width: 30rem) {
    dialog { border-radius: 12px 12px 0 0; margin: auto 0 0; max-height: calc(100dvh - 1rem); max-width: none; padding: var(--modal-padding, 1rem); width: 100%; }
  }
</style>
