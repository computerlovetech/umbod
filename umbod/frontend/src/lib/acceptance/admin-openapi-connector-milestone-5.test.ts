import { render } from 'svelte/server';
import { Window } from 'happy-dom';
import { describe, expect, test, vi } from 'vitest';
import type { OpenApiOperationToolUiModel } from '$lib/admin/openapi-connectors';
import OpenApiOperationCatalog from '$lib/components/admin/openapi-connectors/OpenApiOperationCatalog.svelte';

function createTools(count: number): OpenApiOperationToolUiModel[] {
  const methods = ['get', 'POST', 'patch'];
  return Array.from({ length: count }, (_, index) => ({
    operationId: `operation-${index + 1}`,
    method: methods[index % methods.length],
    path: `/resources/${index + 1}`,
    summary: `Resource ${index + 1}`,
    description: `Resource description ${index + 1}`,
    activationStatus: index % 2 === 0 ? 'enabled' : 'disabled',
    outputSchema: { status: 'not-declared' },
    parameters: [{ name: `resource_id_${index + 1}`, label: 'Resource ID', type: 'string', description: 'Resource identifier', required: true }]
  }));
}

describe('OpenAPI connector administration milestone 5', () => {
  test('tool catalog renders accessible controls and the first page of imported tools', () => {
    const { body } = render(OpenApiOperationCatalog, {
      props: { connectorId: 'billing', tools: createTools(45) }
    });

    expect(body).toMatch(/<label[^>]*>\s*<span>Search tools<\/span>\s*<input[^>]*type="search"/);
    const controls = body.replace(/<!--[\s\S]*?-->/g, '');
    expect(controls).toMatch(/<label[^>]*>HTTP method<\/label>\s*<button[^>]*role="combobox"[^>]*aria-haspopup="listbox"[^>]*aria-expanded="false"/);
    expect(controls).toMatch(/<label[^>]*>Activation status<\/label>\s*<button[^>]*role="combobox"/);
    expect(controls).toMatch(/<label[^>]*>Tools per page<\/label>\s*<button[^>]*role="combobox"[^>]*value="20"/);
    expect(body).not.toContain('<select name="methodFilter"');
    expect(body).not.toContain('<select name="statusFilter"');
    expect(body).toContain('Showing 45 of 45 tools');
    expect(body.match(/<li>/g)).toHaveLength(20);
    expect(body.match(/<article class="tool-card\b[^">]*">/g)).toHaveLength(20);
    expect(body).toMatch(/<ul class="tool-list\b/);
    expect(body).toContain('1 parameter · 1 required');
    expect(body).toContain('Resource identifier');
    expect(body).toContain('operation-20');
    expect(body).not.toContain('operation-21');
    const document = new Window().document;
    document.body.innerHTML = body;
    const pagination = document.querySelector('nav[aria-label="Tool catalog pagination"]');
    const previous = pagination?.querySelector('button:first-of-type');
    const next = pagination?.querySelector('button:last-of-type');
    expect(previous?.textContent).toBe('Previous');
    expect(previous?.getAttribute('type')).toBe('button');
    expect(previous?.hasAttribute('disabled')).toBe(true);
    expect(body).toMatch(/<span[^>]*>Page 1 of 3<\/span>/);
    expect(next?.textContent).toBe('Next');
    expect(next?.getAttribute('type')).toBe('button');
    expect(next?.hasAttribute('disabled')).toBe(false);
  });

  test('tool catalog method choices come from imported tool methods', () => {
    const { body } = render(OpenApiOperationCatalog, {
      props: { connectorId: 'billing', tools: createTools(3) }
    });

    expect(body).toMatch(/<button[^>]*role="combobox"[^>]*value="all"[^>]*>\s*<span>All methods<\/span>/);
    expect(body).not.toContain('<select name="methodFilter"');
  });

  test('empty tool catalog explains that no tools have been imported', () => {
    const { body } = render(OpenApiOperationCatalog, {
      props: { connectorId: 'billing', tools: [] }
    });

    expect(body).toContain('Showing 0 of 0 tools');
    expect(body).toContain('No tools have been imported for this connector.');
    expect(body).not.toMatch(/<ul class="tool-list\b/);
  });

});
