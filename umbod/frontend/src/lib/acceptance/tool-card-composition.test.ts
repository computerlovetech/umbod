import { readFileSync } from 'node:fs';
import { createRawSnippet, type Snippet } from 'svelte';
import { render } from 'svelte/server';
import { describe, expect, test } from 'vitest';
import type { CatalogueCapability } from '$lib/dashboard/domain/schemas';
import type { ToolParameter } from '$lib/components/shared/tools/presentation';
import ToolCard from '$lib/components/shared/tools/ToolCard.svelte';
import AdminToolCard from '$lib/components/admin/connectors/ToolCard.svelte';
import CatalogueToolCard from '$lib/components/dashboard/CatalogueToolCard.svelte';

function content(markup: string): Snippet {
  return createRawSnippet(() => ({ render: (): string => markup }));
}

const parameters: ToolParameter[] = [{ name: 'query', label: 'Query', type: 'string', description: 'Text to find', required: true }];
const capability: Extract<CatalogueCapability, { kind: 'tool' }> = {
  kind: 'tool', key: 'lookup', name: 'Lookup', description: 'User lookup description',
  input_schema: { type: 'object', properties: { query: { type: 'string', description: 'Text to find' } }, required: ['query'] },
  output_schema: { status: 'present', schema: { type: 'object', properties: { result: { type: 'string' } } } }
};

describe('actor-independent tool card composition', () => {
  test('the shared layout renders identity without choosing description or schema policy', (): void => {
    const body = render(ToolCard, { props: { title: 'Lookup', name: 'lookup' } }).body;
    expect(body).toContain('class="tool-card');
    expect(body).toContain('title="Lookup"');
    expect(body).toContain('lookup</code>');
    expect(body).not.toContain('<details');
    expect(body).not.toContain('Not declared');
    expect(body).not.toContain('Output schema');
    expect(body).not.toContain('<button');
  });

  test('callers supply all variable sections in the shared card layout', (): void => {
    const body = render(ToolCard, { props: {
      title: 'Lookup', name: 'lookup',
      description: content('<p>Actor description</p>'),
      parameters: content('<section>Actor input presentation</section>'),
      outputSchema: content('<section>Actor output presentation</section>'),
      controls: content('<button type="button">Actor action</button>')
    } }).body;
    for (const value of ['Actor description', 'Actor input presentation', 'Actor output presentation', 'Actor action']) {
      expect(body.split(value)).toHaveLength(2);
    }
    expect(body.indexOf('Actor action')).toBeLessThan(body.indexOf('Actor description'));
    expect(body.indexOf('Actor description')).toBeLessThan(body.indexOf('Actor input presentation'));
    expect(body.indexOf('Actor input presentation')).toBeLessThan(body.indexOf('Actor output presentation'));
    expect(body).not.toContain('No parameters');
    expect(body).not.toContain('Not declared');
  });

  test('one supplied section can change without altering the other sections', (): void => {
    const props = {
      title: 'Lookup', name: 'lookup',
      parameters: content('<section>Unchanged input</section>'),
      outputSchema: content('<section>Unchanged output</section>')
    };
    const admin = render(ToolCard, { props: { ...props, description: content('<p>Administrative description</p>') } }).body;
    const user = render(ToolCard, { props: { ...props, description: content('<details><summary>User description</summary><p>User guidance</p></details>') } }).body;
    expect(admin).toContain('Administrative description');
    expect(admin).not.toContain('User guidance');
    expect(user).toContain('User guidance');
    expect(user).not.toContain('Administrative description');
    for (const body of [admin, user]) {
      expect(body).toContain('Unchanged input');
      expect(body).toContain('Unchanged output');
      expect(body).not.toContain('<button');
    }
  });

  test('admin composition retains supplied management controls and schema defaults', (): void => {
    const body = render(AdminToolCard, { props: {
      title: 'Lookup', name: 'lookup', description: 'Administrative description', parameters,
      controls: content('<button type="button">Manage tool</button>')
    } }).body;
    expect(body).toContain('Manage tool');
    expect(body).toContain('Administrative description');
    expect(body).toContain('1 parameter');
    expect(body).toContain('1 required');
    expect(body).toContain('Text to find');
    expect(body).toContain('Not declared');
    expect(body).not.toContain('Full input schema');
    expect(body).not.toContain('User lookup description');
  });

  test('user composition chooses full execution schemas without inheriting admin controls', (): void => {
    const body = render(CatalogueToolCard, { props: { capability } }).body;
    expect(body).toContain('User lookup description');
    expect(body).toContain('1 parameter');
    expect(body).toContain('Full input schema (read-only)');
    expect(body).toContain('readonly');
    expect(body).toContain('Available');
    expect(body).toContain('result');
    expect(body).not.toContain('Manage tool');
    expect(body).not.toContain('<button');
    expect(body).not.toContain('Not declared');
  });

  test('actor adapters preserve declared empty output schemas', (): void => {
    const admin = render(AdminToolCard, { props: {
      title: 'Lookup', name: 'lookup', description: '', parameters: [], outputSchema: { status: 'available', schema: {} }
    } }).body;
    const user = render(CatalogueToolCard, { props: { capability: { ...capability, output_schema: { status: 'present', schema: {} } } } }).body;
    for (const body of [admin, user]) {
      expect(body).toContain('Available');
      expect(body).not.toContain('Not declared');
    }
  });

  test.each(['ToolCard.svelte', 'ToolDescription.svelte', 'ToolParameterDetails.svelte', 'ToolOutputSchemaDetails.svelte', 'presentation.ts', 'json-schema-tool-parameters.ts'])('neutral presenter %s does not depend on actor modules', (file): void => {
    const source = readFileSync(`src/lib/components/shared/tools/${file}`, 'utf8');
    expect(source).not.toMatch(/from\s+['"][^'"]*\/(?:admin|dashboard|personal-connections)\//);
  });

  test('the user tool adapter never reaches through the admin presentation or models', (): void => {
    const source = readFileSync('src/lib/components/dashboard/CatalogueToolCard.svelte', 'utf8');
    expect(source).not.toContain('$lib/admin/');
    expect(source).not.toContain('$lib/components/admin/');
  });
});
