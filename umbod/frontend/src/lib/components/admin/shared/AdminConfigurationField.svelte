<script lang="ts">
  import type { HTMLInputAttributes } from 'svelte/elements';

  type InputType = 'text' | 'password' | 'url';

  let {
    id,
    name,
    label,
    type = 'text',
    value = '',
    required = false,
    configuredSecret = false,
    unsupported = false,
    readonly = false,
    autocomplete,
    pattern,
    placeholder,
    helperText,
    describedBy,
    invalid = false,
    oninput
  }: {
    id: string;
    name: string;
    label: string;
    type?: InputType;
    value?: string;
    required?: boolean;
    configuredSecret?: boolean;
    unsupported?: boolean;
    readonly?: boolean;
    autocomplete?: HTMLInputAttributes['autocomplete'];
    pattern?: string;
    placeholder?: string;
    helperText?: string;
    describedBy?: string;
    invalid?: boolean;
    oninput?: (event: Event) => void;
  } = $props();

  const helperId = $derived(helperText || configuredSecret ? `${id}-helper` : undefined);
  const ariaDescribedBy = $derived([describedBy, helperId].filter(Boolean).join(' ') || undefined);
</script>

<div class="configuration-field">
  <label for={id}>{label}</label>
  {#if unsupported}
    <p class="unsupported">{label} cannot be configured in this interface.</p>
  {:else}
    <input
      {id}
      {name}
      {type}
      {autocomplete}
      {pattern}
      {placeholder}
      required={required && !configuredSecret}
      {readonly}
      {value}
      {oninput}
      aria-describedby={ariaDescribedBy}
      aria-invalid={invalid || undefined}
    />
    {#if helperId}
      <p class="helper" id={helperId}>{helperText ?? 'Leave blank to keep the existing secret.'}</p>
    {/if}
  {/if}
</div>

<style>
  .configuration-field {
    display: grid;
    gap: 7px;
  }

  label {
    color: var(--admin-ink);
    font-size: 13px;
    font-weight: 650;
    line-height: 1.4;
  }

  input {
    box-sizing: border-box;
    background: var(--admin-panel);
    border: 1px solid var(--admin-border-strong);
    border-radius: var(--admin-radius);
    color: var(--admin-ink);
    font: inherit;
    font-size: 14px;
    line-height: 1.4;
    min-width: 0;
    padding: 10px 12px;
    width: 100%;
  }

  input:focus {
    border-color: var(--admin-accent);
    outline: 3px solid var(--admin-focus);
  }

  input[readonly] {
    background: var(--admin-soft);
    color: var(--admin-muted);
  }

  input[aria-invalid='true'] {
    border-color: var(--admin-danger);
  }

  .helper,
  .unsupported {
    border-radius: 8px;
    font-size: 13px;
    line-height: 1.5;
    margin: 0;
  }

  .helper {
    color: var(--admin-muted);
  }

  .unsupported {
    background: var(--admin-warning-bg);
    border: 1px solid var(--admin-warning-border);
    color: var(--admin-warning-text);
    padding: 9px 10px;
  }
</style>
