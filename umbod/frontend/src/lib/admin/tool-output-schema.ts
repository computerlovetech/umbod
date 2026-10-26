import type { ToolOutputSchemaState } from '$lib/components/shared/tools/presentation';

export function normalizeNullableToolOutputSchema(
  schema: Record<string, unknown> | null
): ToolOutputSchemaState {
  return schema === null ? { status: 'not-declared' } : { status: 'available', schema };
}

export function normalizeDeclaredToolOutputSchema(
  state:
    | { output_schema_status: 'absent' }
    | { output_schema_status: 'present'; output_schema: Record<string, unknown> }
): ToolOutputSchemaState {
  return state.output_schema_status === 'present'
    ? { status: 'available', schema: state.output_schema }
    : { status: 'not-declared' };
}
