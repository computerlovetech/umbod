<script lang="ts">
  import Button from '$lib/components/admin/shared/Button.svelte';
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
  <Button variant="secondary" type="button" onclick={onPrevious} disabled={!canGoPrevious}>Previous</Button>
  <span>Page {page} of {pageCount}</span>
  <Button variant="secondary" type="button" onclick={onNext} disabled={!canGoNext}>Next</Button>
</nav>

<style>
  .pagination { align-items: center; display: flex; flex-wrap: wrap; gap: 0.75rem; justify-content: center; margin-top: 1rem; }
  span { color: var(--admin-muted); font-size: 0.875rem; min-width: 7rem; text-align: center; }
  @media (max-width: 42rem) { .pagination { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); } span { grid-column: 1 / -1; grid-row: 1; } }
</style>
