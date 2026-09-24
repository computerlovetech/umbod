<script lang="ts">
  import AdminModalShell from '$lib/components/admin/shared/AdminModalShell.svelte';
  import Button from './Button.svelte';

  type Props = {
    open: boolean;
    title: string;
    description: string;
    confirmLabel: string;
    action: string;
    domain: string;
    oncancel: () => void;
  };

  let { open, title, description, confirmLabel, action, domain, oncancel }: Props = $props();
</script>

{#if open}
  <AdminModalShell
    {title}
    titleId="confirmation-title"
    descriptionId="confirmation-description"
    close={oncancel}
  >
    <p id="confirmation-description">{description}</p>
    <div class="actions">
      <Button variant="secondary" onclick={oncancel}>Cancel</Button>
      <form method="POST" {action}>
        <input type="hidden" name="domain" value={domain} />
        <Button variant="danger" type="submit">{confirmLabel}</Button>
      </form>
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
    gap: 0.5rem;
    justify-content: flex-end;
    margin-top: 1.5rem;
  }

  .actions form {
    margin: 0;
  }

</style>
