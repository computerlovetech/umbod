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
    color: #37352f;
    font-size: 13px;
    font-weight: 650;
    line-height: 1.4;
  }

  input {
    background: #fff;
    border: 1px solid #d9d9d6;
    border-radius: 8px;
    color: #37352f;
    font: inherit;
    font-size: 14px;
    line-height: 1.4;
    padding: 9px 10px;
  }

  input:focus {
    border-color: #787774;
    outline: 3px solid rgb(55 53 47 / 12%);
  }

  .helper,
  .unsupported {
    border-radius: 8px;
    font-size: 13px;
    line-height: 1.5;
    margin: 0;
  }

  .helper {
    color: #787774;
  }

  .unsupported {
    background: #fbf3db;
    border: 1px solid #ead9a9;
    color: #7a5d16;
    padding: 9px 10px;
  }
</style>
