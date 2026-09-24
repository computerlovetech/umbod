import { describe, expect, test } from 'vitest';
import { readFileSync } from 'node:fs';

const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');

describe('shared capability description override UI', () => {
  test.each([
    ['native catalog', '../components/admin/connectors/ConnectorList.svelte'],
    ['downstream workspace', '../components/admin/downstream-mcp-connectors/DownstreamMcpWorkspace.svelte'],
    ['OpenAPI workspace', '../components/admin/openapi-connectors/OpenApiConnectorList.svelte']
  ])('uses a separate capability description menu action and modal in %s', (_label, path) => {
    const text = source(path);
    expect(text).toContain('Edit capability description');
    expect(text).toContain('CapabilityDescriptionOverrideModal');
    expect(text).not.toContain('<CapabilityDescriptionOverrideForm');
    expect(text).toContain('Configure');
  });

  test('dedicated modal retains the reusable override editor behavior', () => {
    const modal = source('../components/admin/capability-descriptions/CapabilityDescriptionOverrideModal.svelte');
    const editor = source('../components/admin/capability-descriptions/CapabilityDescriptionOverrideForm.svelte');

    expect(modal).toContain('AdminModalShell');
    expect(modal).toContain('<CapabilityDescriptionOverrideForm');
    expect(modal).toContain('Edit capability description');
    expect(editor).toContain('Default description');
    expect(editor).toContain('Effective preview');
    expect(editor).toContain('Custom agent-facing description');
    expect(editor).toContain('Save custom description');
    expect(editor).toContain('Use default description');
    expect(editor).toContain('onclick={restore}');
  });

  test('downstream creation explains the default description without override controls', () => {
    const text = source('../components/admin/downstream-mcp-connectors/DownstreamMcpSetupModal.svelte');
    expect(text).toContain('Default capability description');
    expect(text).toContain('You can customize the agent-facing description after creation.');
    expect(text).not.toContain('initialCapabilityOverride');
    expect(text).not.toContain('Initial capability override');
  });

  test('OpenAPI creation retains its initial override controls', () => {
    const text = source('../components/admin/openapi-connectors/OpenApiConnectorCreateForm.svelte');
    expect(text).toContain('initialCapabilityOverride');
    expect(text).toContain('Initial capability override');
  });
});
