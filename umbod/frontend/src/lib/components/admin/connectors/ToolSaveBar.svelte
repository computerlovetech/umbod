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
    background: rgb(255 255 255 / 96%);
    border: 1px solid var(--admin-border);
    border-radius: 10px;
    box-shadow: 0 8px 24px rgb(55 53 47 / 12%);
    display: flex;
    gap: 1rem;
    justify-content: flex-end;
    margin: 0 0 1rem;
    padding: 0.7rem 0.8rem 0.7rem 1rem;
  }

  .save-bar--dirty {
    background: #fffaf5;
    border-color: #e9b872;
    box-shadow: 0 8px 24px rgb(146 64 14 / 14%);
  }

  .save-bar--pending {
    background: #fbfbfa;
  }

  .message {
    color: var(--admin-muted);
    font-size: 0.85rem;
    font-weight: 600;
  }

  .save-bar--dirty .message {
    color: #92400e;
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
