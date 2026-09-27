<script lang="ts">
  import LoadingButton from './LoadingButton.svelte';

  type SaveActionTone = 'success' | 'warning' | 'error' | 'muted' | 'saving';

  let {
    label,
    loadingLabel,
    loading,
    disabled = false,
    message,
    tone,
    icon,
    type = 'submit'
  }: {
    label: string;
    loadingLabel: string;
    loading: boolean;
    disabled?: boolean;
    message: string;
    tone: SaveActionTone;
    icon: string;
    type?: 'button' | 'submit';
  } = $props();
</script>

<div class="admin-save-action">
  <LoadingButton {type} {label} {loadingLabel} {loading} {disabled} />
  <span class={["admin-save-action__status", `admin-save-action__status--${tone}`]} aria-label={message} aria-live="polite" role="status" title={message}>
    {#if tone === 'saving'}
      <span class="admin-save-action__spinner" aria-hidden="true"></span>
    {:else}
      <span aria-hidden="true">{icon}</span>
    {/if}
  </span>
</div>

<style>
  .admin-save-action {
    align-items: center;
    display: inline-flex;
    gap: 12px;
  }

  .admin-save-action__status {
    align-items: center;
    border-radius: 50%;
    display: inline-flex;
    flex-shrink: 0;
    font-size: 14px;
    font-weight: 800;
    height: 28px;
    justify-content: center;
    width: 28px;
  }

  .admin-save-action__status--error {
    background: #fef3f2;
    color: #b42318;
  }

  .admin-save-action__status--muted {
    background: var(--admin-hover);
    color: var(--admin-muted);
  }

  .admin-save-action__status--saving {
    background: var(--admin-hover);
    color: var(--admin-muted);
  }

  .admin-save-action__status--success {
    background: #edf9f4;
    color: #067647;
  }

  .admin-save-action__status--warning {
    background: #fff6ee;
    color: var(--admin-warning-text);
  }

  .admin-save-action__spinner {
    animation: admin-save-action-spin 0.8s linear infinite;
    border: 2px solid rgb(120 119 116 / 30%);
    border-radius: 50%;
    border-top-color: currentColor;
    height: 14px;
    width: 14px;
  }

  @keyframes admin-save-action-spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
