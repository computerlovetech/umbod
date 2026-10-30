<script lang="ts">
  let { message }: { message: string } = $props();
</script>

<p class="connector-list-empty-state">{message}</p>

<style>
  .connector-list-empty-state {
    background: var(--admin-soft);
    border: 1px solid var(--admin-border);
    border-radius: var(--admin-radius);
    color: var(--admin-muted);
    font-size: 14px;
    line-height: 1.55;
    margin: 1.5rem 0 0;
    padding: 1rem;
  }
</style>
