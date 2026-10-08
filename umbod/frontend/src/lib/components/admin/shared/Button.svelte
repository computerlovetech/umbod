<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLButtonAttributes, MouseEventHandler } from 'svelte/elements';

  let {
    children,
    variant = 'primary',
    size = 'normal',
    type = 'button',
    disabled = false,
    onclick,
    'data-operation': operation,
    role,
    title,
    class: className,
    'aria-label': ariaLabel,
    'aria-busy': ariaBusy
  }: {
    children: Snippet;
    variant?: 'primary' | 'secondary' | 'danger';
    size?: 'normal' | 'compact';
    type?: 'button' | 'submit';
    disabled?: boolean;
    onclick?: MouseEventHandler<HTMLButtonElement>;
    'data-operation'?: string;
    role?: HTMLButtonAttributes['role'];
    title?: string;
    class?: string;
    'aria-label'?: string;
    'aria-busy'?: boolean;
  } = $props();
</script>

<button class={["admin-shared-button", `admin-shared-button--${variant}`, `admin-shared-button--${size}`, className]} {type} {disabled} {onclick} data-operation={operation} {role} {title} aria-label={ariaLabel} aria-busy={ariaBusy}>
  {@render children()}
</button>

<style>
  .admin-shared-button {
    align-items: center;
    border: 1px solid transparent;
    border-radius: var(--admin-radius);
    cursor: pointer;
    display: inline-flex;
    font: inherit;
    font-size: 13px;
    font-weight: 600;
    justify-content: center;
    line-height: 1.2;
    min-height: 38px;
    padding: 9px 14px;
    transition: background 0.15s, border-color 0.15s, color 0.15s, opacity 0.15s;
    white-space: nowrap;
  }

  .admin-shared-button--compact {
    min-height: 28px;
    padding: 5px 9px;
  }

  .admin-shared-button--primary {
    background: var(--admin-action);
    color: var(--admin-on-action);
  }

  .admin-shared-button--secondary {
    background: var(--admin-panel);
    border-color: var(--admin-border);
    color: var(--admin-ink);
  }

  .admin-shared-button--danger {
    background: var(--admin-danger);
    color: var(--admin-on-action);
  }

  .admin-shared-button--primary:not(:disabled):hover {
    background: var(--admin-action-hover);
  }

  .admin-shared-button--secondary:not(:disabled):hover {
    background: var(--admin-soft);
    border-color: var(--admin-border-strong);
  }

  .admin-shared-button--danger:not(:disabled):hover {
    background: var(--admin-danger-hover);
  }

  .admin-shared-button:focus-visible {
    outline: 3px solid var(--admin-focus);
    outline-offset: 2px;
  }

  .admin-shared-button:disabled {
    background: var(--admin-disabled-bg);
    border-color: var(--admin-border);
    color: var(--admin-disabled-text);
    cursor: not-allowed;
  }
</style>
