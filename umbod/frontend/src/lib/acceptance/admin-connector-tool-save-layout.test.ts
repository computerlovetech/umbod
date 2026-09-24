import { readFileSync } from 'node:fs';
import { describe, expect, test } from 'vitest';

const nativeCatalog = readFileSync('src/lib/components/admin/connectors/ConnectorList.svelte', 'utf8');
const openApiCatalog = readFileSync('src/lib/components/admin/openapi-connectors/OpenApiOperationCatalog.svelte', 'utf8');
const downstreamMcpCatalog = readFileSync('src/lib/components/admin/downstream-mcp-connectors/DownstreamMcpToolCatalog.svelte', 'utf8');
const saveBar = readFileSync('src/lib/components/admin/connectors/ToolSaveBar.svelte', 'utf8');
const scrollableCatalog = readFileSync('src/lib/components/admin/shared/ScrollableToolCatalog.svelte', 'utf8');

describe('connector tool save visibility acceptance', () => {
  test('keeps tool persistence feedback visible across connector types', () => {
    expect(nativeCatalog).toContain('<ToolSaveBar');
    expect(downstreamMcpCatalog).toContain('<ToolSaveBar');
    expect(openApiCatalog).toContain('<ToolSaveBar');
    expect(openApiCatalog).toContain('?/saveToolActivations');
    expect(openApiCatalog).toContain("catalog.pending ? 'Saving tool changes' : catalog.dirty ? 'Unsaved tool changes' : 'All tool changes saved'");
    expect(openApiCatalog).toContain('disabled={!catalog.dirty || catalog.pending}');
    expect(saveBar).not.toContain('position: sticky');
    expect(nativeCatalog).toContain('<ScrollableToolCatalog');
    expect(downstreamMcpCatalog).toContain('<ScrollableToolCatalog');
    expect(openApiCatalog).toContain('<ScrollableToolCatalog');
    expect(scrollableCatalog).toContain('overflow-y: auto');
  });
});
