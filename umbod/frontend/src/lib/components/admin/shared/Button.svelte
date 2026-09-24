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
    formaction,
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
    formaction?: string;
    role?: HTMLButtonAttributes['role'];
    title?: string;
    class?: string;
    'aria-label'?: string;
    'aria-busy'?: boolean;
  } = $props();
</script>

<button class={["admin-shared-button", `admin-shared-button--${variant}`, `admin-shared-button--${size}`, className]} {type} {disabled} {onclick} {formaction} {role} {title} aria-label={ariaLabel} aria-busy={ariaBusy}>
  {@render children()}
</button>

<style>
  .admin-shared-button {
    align-items: center;
    border: 1px solid transparent;
    border-radius: 6px;
    cursor: pointer;
    display: inline-flex;
    font: inherit;
    font-size: 13px;
    font-weight: 600;
    justify-content: center;
    line-height: 1.2;
    min-height: 32px;
    padding: 7px 12px;
    transition: background 0.15s, border-color 0.15s, color 0.15s, opacity 0.15s;
    white-space: nowrap;
  }

  .admin-shared-button--compact {
    min-height: 28px;
    padding: 5px 9px;
  }

  .admin-shared-button--primary {
    background: #37352f;
    color: #ffffff;
  }

  .admin-shared-button--secondary {
    background: #ffffff;
    border-color: #e9e9e7;
    color: #37352f;
  }

  .admin-shared-button--danger {
    background: var(--admin-danger, #b42318);
    color: #ffffff;
  }

  .admin-shared-button--primary:not(:disabled):hover {
    background: #2f2d28;
  }

  .admin-shared-button--secondary:not(:disabled):hover {
    background: #fafaf9;
    border-color: #d8d7d4;
  }

  .admin-shared-button--danger:not(:disabled):hover {
    background: #962018;
  }

  .admin-shared-button:focus-visible {
    outline: 3px solid rgb(55 53 47 / 16%);
    outline-offset: 2px;
  }

  .admin-shared-button:disabled {
    cursor: not-allowed;
    opacity: 0.7;
  }
</style>
