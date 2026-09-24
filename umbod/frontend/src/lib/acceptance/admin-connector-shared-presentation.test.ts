import { readFileSync } from 'node:fs';
import { describe, expect, test } from 'vitest';

const connectorPage = readFileSync('src/routes/admin/connectors/+page.svelte', 'utf8');
const openApiPage = readFileSync('src/routes/admin/openapi-connectors/+page.svelte', 'utf8');
const downstreamMcpPage = readFileSync('src/lib/components/admin/downstream-mcp-connectors/DownstreamMcpPageContent.svelte', 'utf8');
const downstreamMcpRoute = readFileSync('src/routes/admin/downstream-mcp-connectors/+page.svelte', 'utf8');
const connectorList = readFileSync('src/lib/components/admin/connectors/ConnectorList.svelte', 'utf8');
const openApiConnectorList = readFileSync('src/lib/components/admin/openapi-connectors/OpenApiConnectorList.svelte', 'utf8');
const downstreamMcpWorkspace = readFileSync('src/lib/components/admin/downstream-mcp-connectors/DownstreamMcpWorkspace.svelte', 'utf8');
const nativeState = readFileSync('src/lib/components/admin/connectors/connector-list-state.svelte.ts', 'utf8');
const openApiState = readFileSync('src/lib/components/admin/openapi-connectors/openapi-connector-list-state.svelte.ts', 'utf8');
const downstreamState = readFileSync('src/lib/components/admin/downstream-mcp-connectors/downstream-mcp-workspace-state.svelte.ts', 'utf8');
const selectionController = readFileSync('src/lib/components/admin/shared/selection-detail-controller.svelte.ts', 'utf8');
const pageHeader = readFileSync('src/lib/components/admin/connectors/ConnectorPageHeader.svelte', 'utf8');
const sidebarList = readFileSync('src/lib/components/admin/connectors/ConnectorSidebarList.svelte', 'utf8');
const publicationAction = readFileSync('src/lib/components/admin/connectors/ConnectorPublicationMenuAction.svelte', 'utf8');
const detailSummary = readFileSync('src/lib/components/admin/connectors/ConnectorDetailSummary.svelte', 'utf8');

const connectorPages = [connectorPage, openApiPage, downstreamMcpPage];
const connectorLists = [connectorList, openApiConnectorList];

describe('admin connector shared presentation', () => {
  test('all connector pages compose the shared page header', () => {
    for (const page of connectorPages) {
      expect(page).toContain('import ConnectorPageHeader');
      expect(page).toContain('<ConnectorPageHeader');
      expect(page).not.toContain('<div class="connector-page-header"');
      expect(page).not.toContain('class="add"');
    }

    expect(pageHeader).toContain('class="connector-page-header"');
    expect(pageHeader).toContain('aria-label={addLabel}');
    expect(pageHeader).toContain('onclick={(event) => onadd(event.currentTarget)}');
    expect(pageHeader).toContain('.add:focus-visible');
  });

  test('keeps connector workspaces keyed without effect synchronization', () => {
    expect(connectorPage).toContain('{#key data}');
    expect(openApiPage).toContain('{#key data}');
    expect(downstreamMcpRoute).toContain('{#key data}');
    for (const list of [connectorList, openApiConnectorList, downstreamMcpWorkspace]) expect(list).not.toContain('$effect');
    expect(openApiConnectorList).not.toContain('synchronizeServerData');
  });

  test('all connector workspaces use shared selection detail and centralized URL replacement', () => {
    for (const state of [nativeState, openApiState, downstreamState]) expect(state).toContain('SelectionDetailController');
    expect(selectionController).toContain('MountedDetailProxy');
    for (const component of [connectorList, openApiConnectorList, downstreamMcpWorkspace]) {
      expect(component).not.toContain("searchParams.set('connector'");
      expect(component).not.toContain('function selectConnector');
    }
    expect(connectorList).toContain('BrowserSelectionUrlAdapter');
    expect(openApiConnectorList).toContain('BrowserSelectionUrlAdapter');
    expect(downstreamMcpPage).toContain('BrowserSelectionUrlAdapter');
  });

  test('catalog and OpenAPI lists share sidebar presentation while retaining parent actions', () => {
    for (const list of connectorLists) {
      expect(list).toContain('import ConnectorSidebarList');
      expect(list).toContain('<ConnectorSidebarList');
      expect(list).toContain('{#snippet metadata(');
      expect(list).toContain('{#snippet actions(');
      expect(list).toContain('<AdminSidebarActionMenu');
      expect(list).not.toContain('<ul class="connector-list"');
    }

    expect(sidebarList).toContain('{#each items as item (item.id)}');
    expect(sidebarList).toContain('aria-pressed={selectedId === item.id}');
    expect(sidebarList).toContain('{@render metadata(item)}');
    expect(sidebarList).toContain('{@render actions(item)}');
  });

  test('catalog and OpenAPI lists share publication submission behavior', () => {
    for (const list of connectorLists) {
      expect(list).toContain('import ConnectorPublicationMenuAction');
      expect(list).toContain('<ConnectorPublicationMenuAction');
      expect(list).not.toContain('<form method="POST" action={connector.canPublish');
    }

    expect(publicationAction).toContain('method="POST"');
    expect(publicationAction).toContain('<input type="hidden" name="connectorId"');
    expect(publicationAction).toContain('use:enhance');
    expect(publicationAction).toContain('pendingState.start');
    expect(publicationAction).toContain('pendingState.stop');
    expect(publicationAction).toContain('loadingLabel={`${actionLabel}ing...`}');
    expect(publicationAction).toContain('onrequest(event, connectorName, actionLabel)');
    const requestHandler = openApiConnectorList.slice(
      openApiConnectorList.indexOf('function requestPublicationConfirmation'),
      openApiConnectorList.indexOf('function confirmPublication')
    );
    expect(requestHandler).toContain('publication.request');
    expect(requestHandler).not.toContain('closeMenu');
    expect(openApiConnectorList).toMatch(/function confirmPublication[\s\S]*publication\.confirm\(\);[\s\S]*state\.view\.closeMenu\(\);/);
    expect(openApiConnectorList).toMatch(/function cancelPublication[\s\S]*publication\.cancel\(\);[\s\S]*state\.view\.closeMenu\(\);/);
  });

  test('catalog and OpenAPI lists share detail summary presentation', () => {
    for (const list of connectorLists) {
      expect(list).toContain('import ConnectorDetailSummary');
      expect(list).toContain('<ConnectorDetailSummary');
      expect(list).toContain('{#snippet summary()}');
      expect(list).toContain('{#snippet technicalDetails()}');
      expect(list).not.toContain('<article class="connector-detail"');
    }

    expect(detailSummary).toContain('<article class="connector-detail"');
    expect(detailSummary).toContain('<AdminPublicationStatus');
    expect(detailSummary).toContain('{@render summary()}');
    expect(detailSummary).toContain('<details class="technical-details">');
    expect(detailSummary).toContain('.summary-row');
  });
});
