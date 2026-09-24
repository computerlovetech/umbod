<script lang="ts">
  import type { Snippet } from 'svelte';
  import Select from './Select.svelte';
  import type { SelectOption } from './select-state.svelte';

  let {
    ariaLabel,
    searchLabel,
    searchPlaceholder,
    searchValue,
    onSearchChange,
    statusOptions,
    statusValue,
    onStatusChange,
    pageSizeOptions,
    pageSizeValue,
    onPageSizeChange,
    countText,
    methodOptions,
    methodValue = 'all',
    onMethodChange,
    methodLabel = 'HTTP method',
    statusLabel = 'Activation status',
    pageSizeLabel,
    extraFilter
  }: {
    ariaLabel: string;
    searchLabel: string;
    searchPlaceholder: string;
    searchValue: string;
    onSearchChange: (value: string) => void;
    statusOptions: SelectOption[];
    statusValue: string;
    onStatusChange: (value: string) => void;
    pageSizeOptions: SelectOption[];
    pageSizeValue: string;
    onPageSizeChange: (value: string) => void;
    countText: string;
    methodOptions?: SelectOption[];
    methodValue?: string;
    onMethodChange?: (value: string) => void;
    methodLabel?: string;
    statusLabel?: string;
    pageSizeLabel: string;
    extraFilter?: Snippet;
  } = $props();
</script>

<section class="controls" aria-label={ariaLabel}>
  <label class="control search">
    <span>{searchLabel}</span>
    <input type="search" placeholder={searchPlaceholder} value={searchValue} oninput={(event) => onSearchChange(event.currentTarget.value)} />
  </label>
  {#if methodOptions && onMethodChange}
    <div class="control"><Select options={methodOptions} label={methodLabel} value={methodValue} onchange={onMethodChange} /></div>
  {/if}
  {#if extraFilter}{@render extraFilter()}{/if}
  <div class="control"><Select options={statusOptions} label={statusLabel} value={statusValue} onchange={onStatusChange} /></div>
  <div class="control"><Select options={pageSizeOptions} label={pageSizeLabel} value={pageSizeValue} onchange={onPageSizeChange} /></div>
  <p class="status" aria-live="polite">{countText}</p>
</section>

<style>
  .controls { align-items: end; display: flex; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 1rem; }
  .control { display: grid; flex: 1 1 10rem; font-size: 0.8125rem; font-weight: 600; gap: 0.35rem; min-width: 9rem; }
  .search { flex: 3 1 28rem; min-width: min(100%, 18rem); }
  .control input { background: #fff; border: 1px solid #e9e9e7; border-radius: 6px; color: #37352f; font: inherit; min-height: 2.75rem; padding: 0.65rem 0.7rem; }
  .control input:focus-visible { border-color: #2f6feb; outline: 3px solid rgb(47 111 235 / 24%); outline-offset: 2px; }
  .search input { width: 100%; }
  .status { color: #787774; flex-basis: 100%; font-size: 0.875rem; line-height: 1.5; margin: 0; }
  @media (max-width: 42rem) { .controls { align-items: stretch; flex-direction: column; } .control, .search { flex-basis: auto; min-width: 0; width: 100%; } }
</style>
