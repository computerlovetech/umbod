<script lang="ts">
  import AdminModalShell from '$lib/components/admin/shared/AdminModalShell.svelte';
  import Button from '$lib/components/admin/shared/Button.svelte';

  type Props = {
    open: boolean;
    title: string;
    message: string;
    confirmLabel: string;
    cancelLabel?: string;
    onconfirm: () => void;
    oncancel: () => void;
  };

  let { open, title, message, confirmLabel, cancelLabel = 'Cancel', onconfirm, oncancel }: Props = $props();
</script>

{#if open}
  <AdminModalShell
    {title}
    titleId="publication-confirmation-title"
    descriptionId="publication-confirmation-message"
    close={oncancel}
  >
    <p id="publication-confirmation-message">{message}</p>
    <div class="actions">
      <Button variant="secondary" onclick={oncancel}>{cancelLabel}</Button>
      <Button onclick={onconfirm}>{confirmLabel}</Button>
    </div>
  </AdminModalShell>
{/if}

<style>
  p {
    color: var(--admin-muted, #787774);
    line-height: 1.55;
    margin: 1rem 0 0;
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    justify-content: flex-end;
    margin-top: 1.5rem;
  }

</style>
