import { describe, expect, test } from 'vitest';
import { normalizeDeclaredToolOutputSchema, normalizeNullableToolOutputSchema } from './tool-output-schema';

describe('tool output schema normalization', () => {
  test('preserves an empty declared schema as available', () => {
    expect(normalizeDeclaredToolOutputSchema({ output_schema_status: 'present', output_schema: {} })).toEqual({
      status: 'available',
      schema: {}
    });
    expect(normalizeNullableToolOutputSchema({})).toEqual({ status: 'available', schema: {} });
  });

  test('normalizes both absent wire formats as not declared', () => {
    expect(normalizeDeclaredToolOutputSchema({ output_schema_status: 'absent' })).toEqual({ status: 'not-declared' });
    expect(normalizeNullableToolOutputSchema(null)).toEqual({ status: 'not-declared' });
  });
});
