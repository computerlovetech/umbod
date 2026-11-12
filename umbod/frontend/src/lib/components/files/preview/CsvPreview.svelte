<script lang="ts">
  import type { PreviewProps } from '$lib/files/preview/ports';
  import { CsvPreviewState } from './csv-preview-state.svelte';
  import { csvPreviewMaxColumns, csvPreviewMaxRows } from './csv';
  import TextPreview from './TextPreview.svelte';

  let { content }: PreviewProps = $props();
  const state = new CsvPreviewState((): string => content);
</script>

{#if state.preview.kind === 'invalid'}
  <p role="status">This CSV could not be displayed as a table. Showing plain text.</p>
  <TextPreview {content} />
{:else}
  {#if state.preview.truncated}
    <p role="status">Preview limited to the first {csvPreviewMaxRows} rows and {csvPreviewMaxColumns} columns.</p>
  {/if}
  <div class="csv-preview" role="region" aria-label="CSV preview">
    <table aria-label="CSV content">
      <thead>
        <tr>
          {#each state.preview.columns as column (column)}
            <th scope="col">Column {column}</th>
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each state.preview.rows as row (row.number)}
          <tr>
            {#each row.cells as cell (cell.column)}
              <td>{cell.content}</td>
            {/each}
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  .csv-preview { min-width: 0; max-width: 100%; max-height: 36rem; overflow: auto; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); }
  table { border-collapse: separate; border-spacing: 0; width: 100%; color: var(--admin-ink); font-size: 0.9rem; }
  th, td { padding: 0.5rem 0.75rem; text-align: left; vertical-align: top; border-bottom: 1px solid var(--admin-border); border-right: 1px solid var(--admin-border); }
  th { position: sticky; top: 0; background: var(--admin-soft); white-space: nowrap; }
  td { white-space: pre-wrap; overflow-wrap: anywhere; min-width: 8rem; max-width: 24rem; }
  th:last-child, td:last-child { border-right: 0; }
  tbody tr:last-child td { border-bottom: 0; }
  p { color: var(--admin-muted); }
</style>
