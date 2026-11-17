<script lang="ts">
  import '#lib/styles/form-fields.css';
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
    list,
    pattern,
    placeholder,
    inputPrefix,
    maxlength,
    helperText,
    describedBy,
    invalid = false,
    oninput,
    onblur
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
    list?: string;
    pattern?: string;
    placeholder?: string;
    inputPrefix?: string;
    maxlength?: number;
    helperText?: string;
    describedBy?: string;
    invalid?: boolean;
    oninput?: (event: Event) => void;
    onblur?: (event: FocusEvent) => void;
  } = $props();

  const helperId = $derived(helperText || configuredSecret ? `${id}-helper` : undefined);
  const ariaDescribedBy = $derived([describedBy, helperId].filter(Boolean).join(' ') || undefined);
</script>

<div class="configuration-field form-field">
  <label class="form-field-label" for={id}>{label}</label>
  {#if unsupported}
    <p class="unsupported">{label} cannot be configured in this interface.</p>
  {:else}
    <div class={['input-control', { prefixed: inputPrefix, invalid }]}>
      {#if inputPrefix}<span class="input-prefix" aria-hidden="true">{inputPrefix}</span>{/if}
      <input
        class="form-control"
        {id}
        {name}
        {type}
        {autocomplete}
        {list}
        {pattern}
        {placeholder}
        {maxlength}
        required={required && !configuredSecret}
        {readonly}
        {value}
        {oninput}
        {onblur}
        aria-describedby={ariaDescribedBy}
        aria-invalid={invalid || undefined}
      />
    </div>
    {#if helperId}
      <p class="helper" id={helperId}>{helperText ?? 'Leave blank to keep the existing secret.'}</p>
    {/if}
  {/if}
</div>

<style>
  .input-control { min-width: 0; }
  .input-control > input { display: block; }

  .prefixed {
    background: var(--admin-panel);
    border: 1px solid var(--admin-border-strong);
    border-radius: var(--admin-radius);
    display: flex;
    overflow: hidden;
  }

  .input-prefix {
    align-items: center;
    background: var(--admin-soft);
    border-right: 1px solid var(--admin-border-strong);
    color: var(--admin-muted);
    display: flex;
    font-size: 14px;
    padding: 10px 12px;
    white-space: nowrap;
  }

  .prefixed input { border: 0; border-radius: 0; flex: 1; width: 0; }
  .prefixed input:focus { outline: 0; }
  .prefixed:focus-within { outline: 3px solid var(--admin-focus); outline-offset: 3px; }
  .prefixed.invalid { border-color: var(--admin-danger); }

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
