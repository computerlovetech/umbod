import { describe, expect, test } from 'vitest';
import { mapJsonSchemaToConnectorToolParameters } from './json-schema-tool-parameters';

describe('mapJsonSchemaToConnectorToolParameters', () => {
  test('maps top-level properties, labels, descriptions, requiredness, and schema types', () => {
    expect(mapJsonSchemaToConnectorToolParameters({
      type: 'object',
      required: ['account_id'],
      properties: {
        account_id: { type: 'string', title: 'Account', description: 'Account identifier' },
        tags: { type: 'array', items: { type: 'string' } },
        choice: { oneOf: [{ type: 'string' }, { type: 'number' }] },
        flexible: { type: ['string', 'null'] },
        invalid: true
      }
    })).toEqual([
      { name: 'account_id', label: 'Account', type: 'string', description: 'Account identifier', required: true },
      { name: 'tags', label: 'Tags', type: 'array', description: '', required: false },
      { name: 'choice', label: 'Choice', type: 'string | number', description: '', required: false },
      { name: 'flexible', label: 'Flexible', type: 'string | null', description: '', required: false },
      { name: 'invalid', label: 'Invalid', type: 'unknown', description: '', required: false }
    ]);
  });

  test('maps fields from a single referenced object parameter', () => {
    expect(mapJsonSchemaToConnectorToolParameters({
      type: 'object',
      required: ['draft'],
      properties: {
        draft: { $ref: '#/$defs/UpdateTaskDraft' }
      },
      $defs: {
        UpdateTaskDraft: {
          type: 'object',
          required: ['task_id'],
          properties: {
            task_id: { type: 'integer', title: 'Task ID', description: 'Numeric task ID to update.' },
            title: {
              anyOf: [{ type: 'string' }, { type: 'null' }],
              description: 'New nonempty task title. Omit to leave unchanged.'
            }
          }
        }
      }
    })).toEqual([
      { name: 'task_id', label: 'Task ID', type: 'integer', description: 'Numeric task ID to update.', required: true },
      { name: 'title', label: 'Title', type: 'string | null', description: 'New nonempty task title. Omit to leave unchanged.', required: false }
    ]);
  });

  test('maps fields from a single inline object parameter', () => {
    expect(mapJsonSchemaToConnectorToolParameters({
      type: 'object',
      properties: {
        input: {
          type: 'object',
          required: ['query'],
          properties: {
            query: { type: 'string', description: 'Search query.' }
          }
        }
      }
    })).toEqual([
      { name: 'query', label: 'Query', type: 'string', description: 'Search query.', required: true }
    ]);
  });

  test('returns no parameters for malformed and property-less schemas', () => {
    expect(mapJsonSchemaToConnectorToolParameters(null)).toEqual([]);
    expect(mapJsonSchemaToConnectorToolParameters({ type: 'object' })).toEqual([]);
  });
});
