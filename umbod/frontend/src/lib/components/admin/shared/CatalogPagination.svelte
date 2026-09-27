<script lang="ts">
  let { ariaLabel, page, pageCount, canGoPrevious, canGoNext, onPrevious, onNext }: {
    ariaLabel: string;
    page: number;
    pageCount: number;
    canGoPrevious: boolean;
    canGoNext: boolean;
    onPrevious: () => void;
    onNext: () => void;
  } = $props();
</script>

<nav class="pagination" aria-label={ariaLabel}>
  <button type="button" onclick={onPrevious} disabled={!canGoPrevious}>Previous</button>
  <span>Page {page} of {pageCount}</span>
  <button type="button" onclick={onNext} disabled={!canGoNext}>Next</button>
</nav>

<style>
  .pagination { align-items: center; display: flex; flex-wrap: wrap; gap: 0.75rem; justify-content: center; margin-top: 1rem; }
  span { color: var(--admin-muted); font-size: 0.875rem; min-width: 7rem; text-align: center; }
  button { background: var(--admin-panel); border: 1px solid var(--admin-border-strong); border-radius: 6px; color: var(--admin-ink); font: inherit; min-height: 2.75rem; min-width: 6.5rem; padding: 0.5rem 0.875rem; }
  button:focus-visible { border-color: var(--admin-accent); outline: 3px solid var(--admin-focus); outline-offset: 2px; }
  button:not(:disabled) { cursor: pointer; }
  button:disabled { background: var(--admin-soft); border-color: var(--admin-border); color: var(--admin-muted); cursor: not-allowed; }
  @media (max-width: 42rem) { .pagination { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); } span { grid-column: 1 / -1; grid-row: 1; } button { min-width: 0; width: 100%; } }
</style>
