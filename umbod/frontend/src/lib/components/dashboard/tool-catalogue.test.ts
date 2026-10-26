import { render } from 'svelte/server';
import { describe, expect, test } from 'vitest';
import type { CatalogueCapability } from '$lib/dashboard/domain/schemas';
import CatalogueCapabilities from './CatalogueCapabilities.svelte';
import ToolDescription from '$lib/components/shared/tools/ToolDescription.svelte';

const tool: CatalogueCapability = {
  kind: 'tool', key: 'search_meetings', name: 'Search meetings',
  description: 'Find meetings by attendee.',
  input_schema: {
    type: 'object',
    properties: {
      attendee_email: { type: 'string', title: 'Attendee email', description: 'Email address to match' },
      limit: { type: 'integer', description: 'Maximum number of meetings' }
    },
    required: ['attendee_email']
  },
  output_schema: { status: 'present', schema: { type: 'object', properties: { meetings: { type: 'array', items: { type: 'object' } } } } }
};

describe('read-only user tool cards', () => {
  test('composes the shared card with user parameter and output schema disclosures but no administrator controls', (): void => {
    const body = render(CatalogueCapabilities, { props: { capabilities: [tool] } }).body;
    for (const value of ['tool-card', 'Search meetings', 'search_meetings', '2 parameters', '1 required', 'Attendee email', 'Email address to match', 'Full input schema', 'Output schema', 'meetings']) {
      expect(body).toContain(value);
    }
    expect(body).not.toMatch(/role="switch"|role="checkbox"|type="checkbox"/);
    expect(body).not.toContain('Invocation');
    expect(body).not.toContain('Save tools');
    expect(body).toContain('Full input schema (read-only)');
    expect(body).toContain('readonly');
    expect(body).not.toMatch(/<details[^>]*\sopen/);
  });

  test('shows output absence rather than inventing a schema', (): void => {
    const body = render(CatalogueCapabilities, { props: { capabilities: [{ ...tool, output_schema: { status: 'absent' } }] } }).body;
    expect(body).toContain('Not declared');
  });

  test('keeps the complete execution envelope available alongside its parameter summary', (): void => {
    const schema = {
      type: 'object',
      properties: {
        connector_id: { type: 'string', const: 'crm' },
        operation_id: { type: 'string', const: 'search' },
        query: { type: 'object', properties: { query: { type: 'string' } } }
      },
      required: ['connector_id', 'operation_id']
    };
    const body = render(CatalogueCapabilities, { props: { capabilities: [{ ...tool, input_schema: schema }] } }).body;
    for (const value of ['Full input schema', 'connector_id', 'operation_id', 'crm', 'const']) expect(body).toContain(value);
  });
});

describe('shared compact tool descriptions', () => {
  test('long descriptions are collapsed and remain available through an explicit disclosure', (): void => {
    const description = 'Lengthy tool instructions. '.repeat(100);
    const body = render(ToolDescription, { props: { description } }).body;
    expect(body).toContain('aria-hidden="true"');
    expect(body).toContain('class="preview');
    expect(body).toContain('Show full description');
    expect(body).toContain('Hide full description');
    expect(body).toContain(description);
    expect(body).not.toMatch(/<details[^>]*\sopen/);
  });

  test('short descriptions do not add unnecessary disclosure controls', (): void => {
    const body = render(ToolDescription, { props: { description: 'List all meetings.' } }).body;
    expect(body).toContain('List all meetings.');
    expect(body).not.toContain('<details');
  });

  test('empty descriptions do not render placeholders', (): void => {
    const body = render(ToolDescription, { props: { description: '' } }).body;
    expect(body).not.toContain('<p');
    expect(body).not.toContain('<details');
  });
});
