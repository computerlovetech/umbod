import { readFileSync } from 'node:fs';
import { describe, expect, test } from 'vitest';

const connectorPage = readFileSync('src/routes/admin/(connector-workspace)/connectors/+page.svelte', 'utf8');
const openApiPage = readFileSync('src/routes/admin/(connector-workspace)/openapi-connectors/+page.svelte', 'utf8');
const downstreamMcpPage = readFileSync('src/lib/components/admin/downstream-mcp-connectors/DownstreamMcpPageContent.svelte', 'utf8');
const downstreamMcpRoute = readFileSync('src/routes/admin/(connector-workspace)/downstream-mcp-connectors/+page.svelte', 'utf8');
const connectorList = readFileSync('src/lib/components/admin/connectors/ConnectorList.svelte', 'utf8');
const openApiConnectorList = readFileSync('src/lib/components/admin/openapi-connectors/OpenApiConnectorList.svelte', 'utf8');
const downstreamMcpWorkspace = readFileSync('src/lib/components/admin/downstream-mcp-connectors/DownstreamMcpWorkspace.svelte', 'utf8');
const nativeState = readFileSync('src/lib/components/admin/connectors/connector-list-state.svelte.ts', 'utf8');
const openApiState = readFileSync('src/lib/components/admin/openapi-connectors/openapi-connector-list-state.svelte.ts', 'utf8');
const downstreamState = readFileSync('src/lib/components/admin/downstream-mcp-connectors/downstream-mcp-workspace-state.svelte.ts', 'utf8');
const selectionController = readFileSync('src/lib/components/admin/shared/selection-detail-controller.svelte.ts', 'utf8');
const gettingStarted = readFileSync('src/lib/components/getting-started/GettingStarted.svelte', 'utf8');
const sidebarList = readFileSync('src/lib/components/admin/connectors/ConnectorSidebarList.svelte', 'utf8');
const unifiedWorkspace = readFileSync('src/lib/components/admin/connectors/UnifiedConnectorWorkspace.svelte', 'utf8');
const publicationAction = readFileSync('src/lib/components/admin/connectors/ConnectorPublicationMenuAction.svelte', 'utf8');
const detailSummary = readFileSync('src/lib/components/admin/connectors/ConnectorDetailSummary.svelte', 'utf8');

const connectorLayout = readFileSync('src/routes/admin/(connector-workspace)/+layout.svelte', 'utf8');
const connectorLists = [connectorList, openApiConnectorList];

describe('admin connector shared presentation', () => {
  test('connector and getting started pages compose the same neutral subpage container', (): void => {
    for (const page of [connectorLayout, gettingStarted]) {
      expect(page).toContain('import SubpageContainer');
      expect(page).toContain('<SubpageContainer');
      expect(page).not.toContain('ConnectorTabs');
      expect(page).not.toContain('<div class="connector-page-header"');
    }
  });

  test('the shared connector layout owns the sole Add connector trigger', () => {
    expect(connectorLayout).toContain('<AddConnector state={addConnector}');
    for (const page of [connectorPage, openApiPage, downstreamMcpPage]) expect(page).not.toContain('<AddConnector');
  });

  test('mixed workspace owns inventory empty and failure presentation', () => {
    expect(unifiedWorkspace).toContain('<ConnectorListEmptyState {detailLabel}');
    expect(unifiedWorkspace).toContain('Could not load connectors: {unavailableLabels}');
    for (const component of [connectorList, openApiConnectorList, downstreamMcpWorkspace]) {
      expect(component).not.toContain('<ConnectorListEmptyState');
    }
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

  test('connector lists share sidebar presentation while retaining parent actions', () => {
    for (const list of [...connectorLists, downstreamMcpWorkspace]) {
      expect(list).toContain('import UnifiedConnectorWorkspace');
      expect(list).toContain('<UnifiedConnectorWorkspace');
      expect(list).toContain('{#snippet metadata(');
      expect(list).toContain('{#snippet actions(');
      expect(list).toContain('<AdminSidebarActionMenu');
      expect(list).not.toContain('<ul class="connector-list"');
    }

    expect(unifiedWorkspace).toContain('<ConnectorSidebarList');
    expect(unifiedWorkspace).toContain('<AdminSplitWorkspace');
    expect(sidebarList).toContain('{#each rows as row (row.key)}');
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
    expect(publicationAction).toContain('use:browserSubmit');
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
