import { describe, expect, test } from 'vitest';
import {
  promptActivationBatchRequestSchema,
  promptActivationBatchResponseSchema,
  resourceActivationBatchRequestSchema,
  resourceActivationBatchResponseSchema
} from './capability-catalogs';

describe('capability activation batch schemas', () => {
  test('parses prompt batch request and response', () => {
    expect(
      promptActivationBatchRequestSchema.parse({
        prompts: [{ prompt_id: 'summarize', activation_status: 'enabled' }]
      }).prompts[0].prompt_id
    ).toBe('summarize');
    expect(
      promptActivationBatchResponseSchema.parse({
        connector_id: 'test',
        prompts: [{ prompt_id: 'summarize', activation_status: 'disabled' }]
      }).connector_id
    ).toBe('test');
  });

  test('parses resource batch request and response', () => {
    expect(
      resourceActivationBatchRequestSchema.parse({
        resources: [
          { resource_id: 'kb://guide', kind: 'resource', activation_status: 'enabled' },
          {
            resource_id: 'kb://articles/{id}',
            kind: 'resource_template',
            activation_status: 'disabled'
          }
        ]
      }).resources
    ).toHaveLength(2);
    expect(
      resourceActivationBatchResponseSchema.parse({
        connector_id: 'mcp-1',
        resources: [
          { resource_id: 'kb://guide', kind: 'resource', activation_status: 'enabled' }
        ]
      }).resources[0].kind
    ).toBe('resource');
  });
});
