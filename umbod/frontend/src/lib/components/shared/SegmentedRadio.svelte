<script lang="ts">
  let {
    label,
    accessibleName = label,
    options,
    value,
    disabled = false,
    size = 'normal',
    onchange
  }: {
    label: string;
    accessibleName?: string;
    options: readonly { value: string; label: string }[];
    value: string;
    disabled?: boolean;
    size?: 'normal' | 'compact';
    onchange: (value: string) => void;
  } = $props();
  const name = $props.id();
</script>

<fieldset aria-label={accessibleName} data-size={size} {disabled}>
  <legend>{label}</legend>
  <div class="segments">
    {#each options as option (option.value)}
      <label class="option">
        <input type="radio" {name} value={option.value} checked={value === option.value} {disabled} onchange={() => onchange(option.value)} />
        <svg class="check" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" focusable="false"><path d="m3 8 3 3 7-7" /></svg>
        <span>{option.label}</span>
      </label>
    {/each}
  </div>
</fieldset>

<style>
  fieldset { border: 0; margin: 0; min-width: 0; padding: 0; }
  legend { font-size: 0.8125rem; font-weight: 600; margin-bottom: 0.5rem; padding: 0; }
  .segments { background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); display: flex; gap: 0.1875rem; padding: 0.25rem; }
  .option { align-items: center; border-radius: 0.375rem; color: var(--admin-ink); cursor: pointer; display: flex; flex: 1; font-size: 0.875rem; font-weight: 500; gap: 0.4375rem; justify-content: center; padding: 0.6875rem 0.8125rem; position: relative; white-space: nowrap; }
  .option:hover { background: var(--admin-hover); }
  .option:has(input:checked) { background: var(--admin-action-hover); color: var(--admin-on-action); }
  .option:has(input:focus-visible) { outline: 3px solid var(--admin-focus); outline-offset: 3px; }
  .option:has(input:disabled) { cursor: not-allowed; opacity: 0.6; }
  input { height: 1px; opacity: 0; position: absolute; width: 1px; }
  .check { flex-shrink: 0; height: 0.875rem; visibility: hidden; width: 0.875rem; }
  input:checked ~ .check { visibility: visible; }
  [data-size='compact'] legend { font-size: 0.75rem; margin-bottom: 0.375rem; }
  [data-size='compact'] .segments { gap: 0.125rem; padding: 0.1875rem; }
  [data-size='compact'] .option { font-size: 0.8125rem; gap: 0.3125rem; padding: 0.375rem 0.5rem; }
  [data-size='compact'] .check { height: 0.75rem; width: 0.75rem; }
  @media (max-width: 680px) {
    .option { flex: 1 1 auto; font-size: 0.8125rem; gap: 0.3125rem; padding: 0.6875rem 0.4375rem; text-align: center; white-space: normal; }
    .check { height: 0.75rem; width: 0.75rem; }
  }
</style>
