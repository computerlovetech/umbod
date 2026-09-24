import { readFileSync } from 'node:fs';
import { describe, expect, test } from 'vitest';

const sharedShell = readFileSync('src/lib/components/admin/shared/AdminModalShell.svelte', 'utf8');
const select = readFileSync('src/lib/components/admin/shared/Select.svelte', 'utf8');
const openApiModal = readFileSync('src/lib/components/admin/openapi-connectors/OpenApiConnectorSetupModal.svelte', 'utf8');
const publicationModal = readFileSync('src/lib/components/admin/connectors/PublicationConfirmationModal.svelte', 'utf8');
const confirmationDialog = readFileSync('src/lib/components/admin/shared/AdminConfirmationDialog.svelte', 'utf8');
const catalogModal = readFileSync('src/lib/components/admin/connectors/ConnectorCatalogModal.svelte', 'utf8');
const catalogPage = readFileSync('src/routes/admin/connectors/+page.svelte', 'utf8');
const connectorPageHeader = readFileSync('src/lib/components/admin/connectors/ConnectorPageHeader.svelte', 'utf8');
const connectorConfigurationForm = readFileSync('src/lib/components/admin/connectors/ConnectorConfigurationForm.svelte', 'utf8');
const mcpModal = readFileSync('src/lib/components/admin/downstream-mcp-connectors/DownstreamMcpSetupModal.svelte', 'utf8');
const mcpWorkspace = readFileSync('src/lib/components/admin/downstream-mcp-connectors/DownstreamMcpWorkspace.svelte', 'utf8');
const mcpPage = readFileSync('src/lib/components/admin/downstream-mcp-connectors/DownstreamMcpPageContent.svelte', 'utf8');

 describe('admin connector modal consistency', () => {
  test('both setup modals compose the shared accessible shell', () => {
    expect(openApiModal).toContain('import AdminModalShell');
    expect(mcpModal).toContain('import AdminModalShell');
    expect(openApiModal).toContain('<AdminModalShell');
    expect(mcpModal).toContain('<AdminModalShell');
    expect(sharedShell).toContain('role="dialog"');
    expect(sharedShell).toContain('aria-labelledby={titleId}');
    expect(sharedShell).toContain('aria-label="Close"');
    expect(sharedShell).toContain('.close:focus-visible');
    expect(sharedShell).toContain('cursor: pointer');
  });

  test('confirmation dialogs compose the same shared shell', () => {
    expect(publicationModal).toContain('import AdminModalShell');
    expect(publicationModal).toContain('<AdminModalShell');
    expect(publicationModal).toContain('descriptionId="publication-confirmation-message"');
    expect(confirmationDialog).toContain('import AdminModalShell');
    expect(confirmationDialog).toContain('<AdminModalShell');
    expect(publicationModal).not.toContain('class="backdrop"');
    expect(confirmationDialog).not.toContain('class="backdrop"');
    expect(sharedShell).toContain("event.key === 'Escape'");
  });

  test('both modals use the shared select and preserve hidden form values', () => {
    expect(openApiModal).toContain('import Select');
    expect(mcpModal).toContain('import Select');
    expect(openApiModal).not.toContain('<select');
    expect(openApiModal).toContain('name="authenticationType" value={state.authenticationType}');
    expect(mcpModal).toContain('name="authMode" value={state.authMode}');
    expect(openApiModal).toContain("state.authenticationType === 'bearer'");
    expect(select).toContain('role="combobox"');
    expect(select).toContain('role="listbox"');
    expect(select).toContain("style:visibility={state.overlayGeometry ? 'visible' : 'hidden'}");
    expect(select).toContain("event.key === 'ArrowDown'");
    expect(select).toContain('onclick={() => choose(option.value)}');
  });

  test('connector catalog exposes an accessible add flow for only unconfigured connectors', () => {
    expect(catalogPage).toContain('addLabel="Add connector"');
    expect(connectorPageHeader).toContain('aria-label={addLabel}');
    expect(catalogPage).toContain('data.connectors.filter((connector) => connector.isConfigured)');
    expect(catalogModal).toContain('connectors.filter((connector) => !connector.isConfigured)');
    expect(catalogModal).toContain('<AdminModalShell');
    expect(catalogModal).toContain('aria-label="Available connectors"');
    expect(catalogModal).toContain('<ConnectorConfigurationForm');
    expect(catalogModal).toContain('onsaved={state.close}');
  });

  test('plugin connector configuration uses the neutral panel treatment', () => {
    expect(connectorConfigurationForm).toContain('class="configuration admin-panel"');
    expect(connectorConfigurationForm).not.toContain('class="configuration admin-panel admin-panel-accent"');
  });

  test('MCP workspace buttons expose pointer and disabled cursor styles', () => {
    expect(mcpPage).toContain('<ConnectorPageHeader');
    expect(connectorPageHeader).toContain('cursor: pointer');
    expect(mcpWorkspace).toContain('button:not(:disabled){cursor:pointer}');
    expect(mcpWorkspace).toContain('button:disabled{cursor:not-allowed}');
  });
});
