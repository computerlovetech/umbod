<script lang="ts">
  import type { Snippet } from 'svelte';

  let {
    message,
    dirty = false,
    pending = false,
    children
  }: {
    message: string;
    dirty?: boolean;
    pending?: boolean;
    children?: Snippet;
  } = $props();
</script>

<div class={["save-bar", dirty && "save-bar--dirty", pending && "save-bar--pending"]}>
  <span class="message" aria-live="polite">{message}</span>
  {#if children}
    <div class="action">{@render children()}</div>
  {/if}
</div>

<style>
  .save-bar {
    align-items: center;
    background: var(--admin-soft);
    border: 1px solid var(--admin-border);
    border-radius: 10px;
    display: flex;
    gap: 1rem;
    justify-content: flex-end;
    margin: 0 0 1rem;
    padding: 0.7rem 0.8rem 0.7rem 1rem;
  }

  .save-bar--dirty {
    background: var(--admin-warning-bg);
    border-color: var(--admin-warning-border);
  }

  .save-bar--pending {
    background: var(--admin-soft);
  }

  .message {
    color: var(--admin-muted);
    font-size: 0.85rem;
    font-weight: 600;
  }

  .save-bar--dirty .message {
    color: var(--admin-warning-text);
  }

  .action {
    flex: 0 0 auto;
  }

  @media (max-width: 640px) {
    .save-bar {
      align-items: stretch;
      flex-direction: column;
      gap: 0.55rem;
    }

    .action {
      align-self: stretch;
    }

    .action :global(.admin-save-action) {
      justify-content: space-between;
      width: 100%;
    }
  }
</style>
