import { readFileSync } from 'node:fs';
import { describe, expect, test } from 'vitest';

const controls = readFileSync('src/lib/components/admin/downstream-mcp-connectors/DownstreamMcpWorkspace.svelte', 'utf8');
const route = readFileSync('src/routes/admin/downstream-mcp-connectors/+page.server.ts', 'utf8');
const page = readFileSync('src/lib/components/admin/downstream-mcp-connectors/DownstreamMcpPageContent.svelte', 'utf8');
const pageRoute = readFileSync('src/routes/admin/downstream-mcp-connectors/+page.svelte', 'utf8');
const setupModal = readFileSync('src/lib/components/admin/downstream-mcp-connectors/DownstreamMcpSetupModal.svelte', 'utf8');
const toolToggle = readFileSync('src/lib/components/admin/downstream-mcp-connectors/DownstreamMcpToolActivationToggle.svelte', 'utf8');
const toolCatalog = readFileSync('src/lib/components/admin/downstream-mcp-connectors/DownstreamMcpToolCatalog.svelte', 'utf8');
const openApiToolToggle = readFileSync('src/lib/components/admin/openapi-connectors/OpenApiToolActivationToggle.svelte', 'utf8');

describe('downstream MCP connector administration', () => {
  test('captures and displays the connector capability description', () => {
    expect(setupModal).toContain('name="capabilityDescription"');
    expect(setupModal).toContain('label="Default capability description"');
    expect(controls).toContain('detailSelected.capability_description');
    expect(route).toContain("data.get('capabilityDescription')");
  });

  test('offers publication and per-tool activation controls with pending and error feedback', () => {
    expect(controls).toContain("'unpublish' : 'publish'");
    expect(controls).toContain("import ConnectorPublicationMenuAction");
    expect(controls).toContain("import PublicationConfirmationModal");
    expect(controls).toContain('<ConnectorPublicationMenuAction');
    expect(controls).toContain('<PublicationConfirmationModal');
    expect(controls).toContain('the MCP proxy connector');
    expect(controls).toContain('confirmLabel={state.pendingPublication?.actionLabel');
    expect(controls).toContain('DownstreamMcpToolCatalog');
    expect(toolCatalog).toContain('DownstreamMcpToolActivationToggle');
    expect(toolCatalog).toContain('searchLabel="Search tools"');
    expect(toolCatalog).toContain('pageSizeLabel="Tools per page"');
    expect(openApiToolToggle).toContain('AdminToggle');
    expect(toolToggle).toContain('AdminToggle');
    expect(toolCatalog).toContain('onActivationChange={catalog.setToolActivation}');
    expect(toolCatalog).toContain('?/saveToolActivations');
    expect(toolCatalog).toContain('catalog.beginSave()');
    expect(toolCatalog).toContain('catalog.finishSave(');
    expect(controls).toContain('role="alert"');
    expect(controls).toContain('Working…');
  });

  test('uses the shared connector sidebar without exposing connector identifiers', () => {
    expect(controls).toContain('ConnectorSidebarList');
    expect(controls).toContain('item.connector.health.status} · {item.connector.publication_status');
    expect(controls).not.toContain('<span>{connector.connector_id}</span>');
  });

  test('resets connector-specific tool catalog state when selection changes', () => {
    expect(controls).toContain('{#key detailSelected.connector_id}');
    expect(controls).toContain('connectorId={detailSelected.connector_id} tools={catalog?.tools ?? []}');
  });

  test('recreates page state only when server data changes', () => {
    expect(pageRoute).toContain('{#key data}');
    expect(pageRoute).toContain('<DownstreamMcpPageContent {data} {form} />');
    expect(pageRoute).not.toContain('$effect');
    expect(page).not.toContain('$effect');
  });

  test('shares one create and configure form with the canonical proxy prefix', () => {
    expect(page).not.toContain('name="publicPath"');
    expect(page).toContain('<DownstreamMcpWorkspace');
    expect(setupModal).toContain("configuring ? '?/configure' : '?/create'");
    expect(setupModal).toContain('/mcp/proxies/');
    expect(setupModal).not.toContain('Connector ID');
    expect(setupModal).toContain('name="connectorId" value={connector?.connector_id');
    expect(setupModal).not.toContain('pattern="/mcp/[');
  });

  test('distinguishes the shared aggregate endpoint from the immutable dedicated path', () => {
    expect(setupModal).toContain('>Dedicated MCP path (additional)</label>');
    expect(setupModal).toContain('<span aria-hidden="true">/mcp/proxies/</span>');
    expect(setupModal).toContain('pattern="[a-z0-9][a-z0-9-]');
    expect(setupModal).toContain('After discovery, enable and publish tools to make them available on <code>/mcp</code>');
    expect(setupModal).toContain('Enter only the connector-specific suffix');
    expect(setupModal).toContain('The dedicated MCP path is immutable');
    expect(controls).toContain('<ConnectorDetailItem label="Shared endpoint" variant="detail"><CopyableValue value={sharedMcpUri} /></ConnectorDetailItem>');
    expect(controls).toContain('<ConnectorDetailItem label="Dedicated endpoint" variant="detail"><CopyableValue value={detailSelected.public_url} /></ConnectorDetailItem>');
    expect(controls).toContain("`${new URL(detailSelected.public_url).origin}/mcp`");
    expect(controls).not.toContain('namespaced alongside tools from other connectors');
    expect(controls).not.toContain('Only this connector’s tools appear here, using their original downstream names');
    expect(controls).not.toContain('label="Public MCP path"');
  });

  test('uses shared accessible form controls and retains configured bearer secrets', () => {
    expect(setupModal).toContain("import AdminConfigurationField");
    expect(setupModal).toContain("import Select");
    expect(setupModal).toContain("import LoadingButton");
    expect(setupModal).toContain('accessibleName="Authentication"');
    expect(setupModal).toContain('name="authMode" value={state.authMode}');
    expect(setupModal).toContain("state.authMode === 'static_bearer'");
    expect(setupModal).toContain('configuredSecret={configuring && Boolean(connector?.credential_configured)}');
    expect(setupModal).toContain('autocomplete="new-password" required configuredSecret=');
    expect(setupModal).toContain('loading={state.submitting}');
    expect(setupModal).toContain("downstream-mcp-${configuring ? 'configure' : 'create'}");
    expect(setupModal).not.toContain('<select');
  });

  test('routes control actions through the composite API adapter', () => {
    expect(route).toContain('.downstreamMcpConnectors.publish(');
    expect(route).toContain('.downstreamMcpConnectors.unpublish(');
    expect(route).toContain('.downstreamMcpConnectors.saveActivations(');
    expect(route).not.toContain('.downstreamMcpConnectors.enableTool(');
    expect(route).not.toContain('.downstreamMcpConnectors.disableTool(');
    expect(route).toContain('presentDownstreamMcpActionError');
    expect(route).toContain("status: 'unhealthy'");
    expect(route).toContain("values.publicPath === '/mcp'");
    expect(route).toContain("mode: 'create'");
    expect(route).not.toContain('validationMessage(error.body)');
    expect(route).not.toContain('validationMessages');
  });
});
