import Papa from 'papaparse';

export interface CsvCell {
  readonly column: number;
  readonly content: string;
}

export interface CsvRow {
  readonly number: number;
  readonly cells: readonly CsvCell[];
}

export type CsvPreview =
  | { readonly kind: 'invalid' }
  | { readonly kind: 'table'; readonly columns: readonly number[]; readonly rows: readonly CsvRow[]; readonly truncated: boolean };

export const csvPreviewMaxRows = 200;
export const csvPreviewMaxColumns = 50;

export function prepareCsvPreview(content: string): CsvPreview {
  const parsed = Papa.parse<string[]>(content, {
    delimiter: ',',
    header: false,
    dynamicTyping: false,
    skipEmptyLines: true,
    preview: csvPreviewMaxRows + 1
  });
  if (parsed.errors.length > 0) return { kind: 'invalid' };
  const visibleRows = parsed.data.slice(0, csvPreviewMaxRows);
  const columnCount = Math.min(csvPreviewMaxColumns, Math.max(0, ...visibleRows.map((row: string[]): number => row.length)));
  const columns = Array.from({ length: columnCount }, (_value: unknown, index: number): number => index + 1);
  return {
    kind: 'table',
    columns,
    rows: visibleRows.map((row: string[], index: number): CsvRow => ({
      number: index + 1,
      cells: columns.map((column: number): CsvCell => ({ column, content: row[column - 1] ?? '' }))
    })),
    truncated: parsed.data.length > csvPreviewMaxRows || visibleRows.some((row: string[]): boolean => row.length > csvPreviewMaxColumns)
  };
}
