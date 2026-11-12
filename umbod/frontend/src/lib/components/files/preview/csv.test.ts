import { expect, test } from 'vitest';
import { prepareCsvPreview, type CsvCell, type CsvRow } from './csv';

test.each<[string, string[][]]>([
  ['name,value\nAlice,42', [['name', 'value'], ['Alice', '42']]],
  ['"one,two","say ""hello"""\r\n"line one\r\nline two",end\r\n', [['one,two', 'say "hello"'], ['line one\r\nline two', 'end']]],
  ['\uFEFF名前,値\r\n日本語,🌍', [['名前', '値'], ['日本語', '🌍']]],
  ['a,b,\n\nc\n,d,e,\n', [['a', 'b', '', ''], ['c', '', '', ''], ['', 'd', 'e', '']]],
  ['001,false\n=SUM(A1:A2),<script>alert(1)</script>', [['001', 'false'], ['=SUM(A1:A2)', '<script>alert(1)</script>']]],
  ['a;b\nx\ty', [['a;b'], ['x\ty']]],
  ['', []],
  ['\r\n\r\n', []]
])('parses comma-separated data without guessing headers: %j', (content: string, rows: string[][]): void => {
  const columnCount = rows[0]?.length ?? 0;
  expect(prepareCsvPreview(content)).toEqual({
    kind: 'table',
    columns: Array.from({ length: columnCount }, (_value: unknown, index: number): number => index + 1),
    rows: rows.map((cells: string[], index: number): CsvRow => ({
      number: index + 1,
      cells: cells.map((value: string, column: number): CsvCell => ({ column: column + 1, content: value }))
    })),
    truncated: false
  });
});

test.each(['"unterminated,value', '"closed"unexpected,value'])('rejects malformed quoted CSV: %j', (content: string): void => {
  expect(prepareCsvPreview(content)).toEqual({ kind: 'invalid' });
});

test.each([200, 201])('limits %i rows to the first 200 and reports only actual truncation', (count: number): void => {
  const preview = prepareCsvPreview(Array.from({ length: count }, (_value: unknown, index: number): string => `row-${index + 1},value`).join('\n'));
  expect(preview.kind).toBe('table');
  if (preview.kind !== 'table') throw new Error('Expected CSV table');
  expect(preview.rows).toHaveLength(200);
  expect(preview.rows[0]).toEqual({ number: 1, cells: [{ column: 1, content: 'row-1' }, { column: 2, content: 'value' }] });
  expect(preview.rows[199]).toEqual({ number: 200, cells: [{ column: 1, content: 'row-200' }, { column: 2, content: 'value' }] });
  expect(preview.truncated).toBe(count > 200);
});

test.each([50, 51])('limits %i columns to the first 50 and reports only actual truncation', (count: number): void => {
  const preview = prepareCsvPreview(Array.from({ length: count }, (_value: unknown, index: number): string => `value-${index + 1}`).join(','));
  expect(preview.kind).toBe('table');
  if (preview.kind !== 'table') throw new Error('Expected CSV table');
  expect(preview.columns).toEqual(Array.from({ length: 50 }, (_value: unknown, index: number): number => index + 1));
  expect(preview.rows[0].cells).toHaveLength(50);
  expect(preview.rows[0].cells[49]).toEqual({ column: 50, content: 'value-50' });
  expect(preview.truncated).toBe(count > 50);
});
