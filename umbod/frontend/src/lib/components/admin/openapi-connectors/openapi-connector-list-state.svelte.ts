import type { OpenApiConnectorDetailBundle } from '$lib/admin/openapi-connector-details-browser-api';
import type { InvocationPolicyTool } from '$lib/admin/invocation-policy';
import type { OpenApiConnectorListItem } from '$lib/admin/openapi-connectors';
import { SelectionDetailController } from '$lib/components/admin/shared/selection-detail-controller.svelte';
import { InMemorySelectionUrlAdapter, type SelectionUrlPort } from '$lib/components/admin/shared/selection-url-port';
import { OpenApiConnectorListViewState } from './openapi-connector-list-view-state.svelte';
import { OpenApiToolCatalogState, type OpenApiToolLoader } from './openapi-tool-catalog-state.svelte';

export type { OpenApiToolsLoadState } from './openapi-tool-catalog-state.svelte';

type DetailLoader = (connectorId: string, signal?: AbortSignal) => Promise<OpenApiConnectorDetailBundle | OpenApiConnectorListItem>;

type OpenApiConnectorListStateOptions = {
  connectors?: OpenApiConnectorListItem[];
  initialConnectorId?: string | null;
  loadTools?: OpenApiToolLoader;
  loadDetail?: DetailLoader;
  initialDetail?: OpenApiConnectorListItem;
  initialInvocationPolicies?: InvocationPolicyTool[];
  initialDetailFailed?: boolean;
  selectionUrl?: SelectionUrlPort;
};

export class OpenApiConnectorListState {
  readonly view = new OpenApiConnectorListViewState();
  readonly tools: OpenApiToolCatalogState;
  private readonly selection: SelectionDetailController<OpenApiConnectorListItem, OpenApiConnectorListItem>;
  private policiesByConnectorId = $state.raw<Record<string, InvocationPolicyTool[]>>({});

  get selectedConnectorId(): string | null { return this.selection.selectedId; }
  get detailLoading(): boolean { return this.selection.loading; }
  get detailFailed(): boolean { return this.selection.failed; }

  constructor(options: OpenApiConnectorListStateOptions = {}) {
    this.selection = new SelectionDetailController({
      items: options.connectors ?? [],
      itemId: (connector) => connector.id,
      selectedId: options.initialConnectorId,
      initialDetail: options.initialDetail,
      initialDetailFailed: options.initialDetailFailed,
      loadDetail: options.loadDetail ? async (connectorId, signal) => {
        const bundle = await options.loadDetail!(connectorId, signal);
        if ('connector' in bundle) {
          this.policiesByConnectorId = { ...this.policiesByConnectorId, [connectorId]: bundle.invocationPolicies };
          return bundle.connector;
        }
        return bundle;
      } : undefined,
      allowUnknownSelection: true,
      url: options.selectionUrl ?? new InMemorySelectionUrlAdapter(),
      onSelectionChange: this.view.resetForSelection
    });
    if (options.initialDetail && options.initialInvocationPolicies) {
      this.policiesByConnectorId = { [options.initialDetail.id]: options.initialInvocationPolicies };
    }
    this.tools = new OpenApiToolCatalogState({
      loadTools: options.loadTools,
      detailAccess: {
        readDetail: (connectorId) => this.selection.readDetail(connectorId),
        fetchDetail: options.loadDetail ? (connectorId) => this.selection.fetch(connectorId) : undefined
      }
    });
  }

  policiesFor = (connectorId: string): InvocationPolicyTool[] => this.policiesByConnectorId[connectorId] ?? [];

  resolveSelectedConnector = (connectors?: OpenApiConnectorListItem[]): OpenApiConnectorListItem | null => {
    if (connectors) this.selection.replaceItems(connectors);
    const selected = this.selection.selectedItem;
    return selected ? this.selection.readDetail(selected.id) ?? selected : null;
  };

  selectConnector = (connectorId: string): void => {
    this.selection.select(connectorId);
  };

  retryDetail = (): void => {
    if (this.selectedConnectorId !== null) void this.retrySelectedDetail(this.selectedConnectorId);
  };

  setMenuOpen = (connectorId: string, open: boolean): void => {
    this.view.setMenuOpen(connectorId, open);
    if (open) this.selectConnector(connectorId);
  };

  loadOperations = async (connector: OpenApiConnectorListItem): Promise<void> => {
    this.selectConnector(connector.id);
    if (!this.selection.readDetail(connector.id) && await this.selection.load(connector.id) === null) return;
    if (this.selectedConnectorId === connector.id) await this.tools.load(connector);
  };

  showCapabilityDescription = (connectorId: string): void => {
    this.selectConnector(connectorId);
    this.view.showCapabilityDescription(connectorId);
  };

  toggleOperations = (connector: OpenApiConnectorListItem): void => {
    if (this.view.toggleOperations()) void this.tools.load(connector);
  };

  private retrySelectedDetail = async (connectorId: string): Promise<void> => {
    const detail = await this.selection.fetch(connectorId);
    if (detail !== null && this.selectedConnectorId === connectorId) await this.tools.load(detail);
  };
}
