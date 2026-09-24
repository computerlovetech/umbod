<script lang="ts">
  import type { ToastState, ToastVariant } from './toast-state.svelte';

  let { state }: { state: ToastState } = $props();

  const labels: Record<ToastVariant, string> = {
    success: 'Success',
    warning: 'Warning',
    error: 'Error'
  };

  const icons: Record<ToastVariant, string> = {
    success: '✓',
    warning: '!',
    error: '×'
  };
</script>

<div class="toast-region" aria-label="Notifications">
  {#each state.toasts as toast (toast.id)}
    <div
      class={`toast toast--${toast.variant}`}
      role={toast.variant === 'error' ? 'alert' : 'status'}
      aria-live={toast.variant === 'error' ? 'assertive' : 'polite'}
      aria-atomic="true"
    >
      <span class="toast__icon" aria-hidden="true">{icons[toast.variant]}</span>
      <div class="toast__content">
        <strong>{labels[toast.variant]}</strong>
        <span>{toast.message}</span>
      </div>
      <button type="button" onclick={() => state.dismiss(toast.id)} aria-label={`Dismiss ${labels[toast.variant].toLowerCase()} notification`}>
        <span aria-hidden="true">×</span>
      </button>
    </div>
  {/each}
</div>

<style>
  .toast-region {
    position: fixed;
    z-index: 10000;
    inset-block-start: 1rem;
    inset-inline-end: 1rem;
    display: flex;
    width: min(24rem, calc(100vw - 2rem));
    flex-direction: column;
    gap: 0.75rem;
    pointer-events: none;
  }

  .toast {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: start;
    gap: 0.75rem;
    padding: 0.875rem 1rem;
    border: 1px solid currentColor;
    border-radius: 0.5rem;
    box-shadow: 0 0.5rem 1.5rem rgb(0 0 0 / 20%);
    pointer-events: auto;
    animation: toast-enter 160ms ease-out;
  }

  .toast--success { color: #166534; background: #f0fdf4; }
  .toast--warning { color: #854d0e; background: #fefce8; }
  .toast--error { color: #991b1b; background: #fef2f2; }

  .toast__icon {
    display: grid;
    width: 1.5rem;
    height: 1.5rem;
    place-items: center;
    border: 2px solid currentColor;
    border-radius: 50%;
    font-weight: 700;
    line-height: 1;
  }

  .toast__content { display: grid; gap: 0.125rem; overflow-wrap: anywhere; }
  .toast__content strong { font-size: 0.875rem; }
  .toast__content span { color: #111827; }

  button {
    padding: 0.125rem 0.375rem;
    border: 0;
    border-radius: 0.25rem;
    color: inherit;
    background: transparent;
    cursor: pointer;
    font-size: 1.25rem;
    line-height: 1;
  }

  button:hover { background: rgb(0 0 0 / 8%); }
  button:focus-visible { outline: 2px solid currentColor; outline-offset: 2px; }

  @keyframes toast-enter {
    from { opacity: 0; transform: translateY(-0.5rem); }
  }

  @media (max-width: 30rem) {
    .toast-region { inset-inline: 0.75rem; width: auto; }
  }

  @media (prefers-reduced-motion: reduce) {
    .toast { animation: none; }
  }
</style>
