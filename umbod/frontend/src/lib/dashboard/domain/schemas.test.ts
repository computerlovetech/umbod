import { describe, expect, test } from 'vitest';
import { catalogueCapabilitySchema } from './schemas';

const metadata = { key: 'events', name: 'Events', description: 'Read calendar events' };
const inputSchema = {
  type: 'object',
  properties: { calendar_id: { type: 'string', description: 'Calendar identifier' } },
  required: ['calendar_id']
};

describe('user capability wire contract', () => {
  test('preserves the complete input and declared output schemas of an available tool', (): void => {
    const capability = {
      ...metadata, kind: 'tool',
      input_schema: inputSchema,
      output_schema: { status: 'present', schema: { type: 'array', items: { type: 'string' } } }
    };
    expect(catalogueCapabilitySchema.parse(capability)).toEqual(capability);
  });

  test('keeps undeclared output distinct from a declared empty schema', (): void => {
    const base = { ...metadata, kind: 'tool', input_schema: {} };
    expect(catalogueCapabilitySchema.parse({ ...base, output_schema: { status: 'absent' } })).toEqual({
      ...base, output_schema: { status: 'absent' }
    });
    expect(catalogueCapabilitySchema.parse({ ...base, output_schema: { status: 'present', schema: {} } })).toEqual({
      ...base, output_schema: { status: 'present', schema: {} }
    });
  });

  test.each([
    { ...metadata, kind: 'tool' },
    { ...metadata, kind: 'tool', input_schema: [], output_schema: { status: 'absent' } },
    { ...metadata, kind: 'tool', input_schema: {}, output_schema: { status: 'present' } },
    { ...metadata, kind: 'tool', input_schema: {}, output_schema: { status: 'absent', schema: {} } },
    { ...metadata, kind: 'tool', input_schema: {}, output_schema: null },
    { ...metadata, kind: 'tool', input_schema: {}, output_schema: { status: 'absent' }, configuration: {} }
  ])('rejects incomplete or non-user tool projections %#', (capability): void => {
    expect(catalogueCapabilitySchema.safeParse(capability).success).toBe(false);
  });

  test.each(['prompt', 'resource', 'resource_template'])('keeps %s display metadata separate from tool schemas', (kind): void => {
    expect(catalogueCapabilitySchema.parse({ ...metadata, kind })).toEqual({ ...metadata, kind });
    expect(catalogueCapabilitySchema.safeParse({ ...metadata, kind, input_schema: inputSchema }).success).toBe(false);
  });
});
