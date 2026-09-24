import { BrowserRequestError } from '$lib/admin/infrastructure/browser-request';
import type { OpenApiConnectorListItem, OpenApiOperationToolUiModel, OpenApiToolActivationStatus } from '$lib/admin/openapi-connectors';

export type OpenApiToolsLoadState =
  | { status: 'idle'; tools: OpenApiOperationToolUiModel[] }
  | { status: 'loading'; tools: OpenApiOperationToolUiModel[] }
  | { status: 'ready'; tools: OpenApiOperationToolUiModel[] }
  | { status: 'failed'; tools: OpenApiOperationToolUiModel[] };

export type OpenApiToolLoader = (connectorId: string) => Promise<OpenApiOperationToolUiModel[]>;

export interface OpenApiToolCatalogDetailAccess {
  readDetail(connectorId: string): OpenApiConnectorListItem | undefined;
  fetchDetail?: (connectorId: string) => Promise<OpenApiConnectorListItem | null>;
}

export type OpenApiToolCatalogStateOptions = {
  loadTools?: OpenApiToolLoader;
  detailAccess: OpenApiToolCatalogDetailAccess;
};

export class OpenApiToolCatalogState {
  private toolCache = $state.raw<Record<string, OpenApiToolsLoadState>>({});
  private readonly loadTools: OpenApiToolLoader | null;
  private readonly detailAccess: OpenApiToolCatalogDetailAccess;
  private readonly toolRequestVersions = new Map<string, number>();

  constructor(options: OpenApiToolCatalogStateOptions) {
    this.loadTools = options.loadTools ?? null;
    this.detailAccess = options.detailAccess;
  }

  toolsState = (connector: OpenApiConnectorListItem): OpenApiToolsLoadState =>
    this.toolCache[this.cacheKey(connector)] ?? { status: 'idle', tools: [] };

  load = async (connector: OpenApiConnectorListItem, force = false): Promise<void> => {
    if (this.loadTools === null) return;
    let authoritative = this.detailAccess.readDetail(connector.id);
    if (!authoritative && this.detailAccess.fetchDetail) authoritative = await this.detailAccess.fetchDetail(connector.id) ?? undefined;
    authoritative ??= connector;
    const key = this.cacheKey(authoritative);
    const current = this.toolCache[key];
    if (!force && (current?.status === 'loading' || current?.status === 'ready')) return;
    const requestVersion = (this.toolRequestVersions.get(key) ?? 0) + 1;
    this.toolRequestVersions.set(key, requestVersion);
    this.toolCache = { ...this.toolCache, [key]: { status: 'loading', tools: current?.tools ?? [] } };
    try {
      const tools = await this.loadTools(connector.id);
      if (this.toolRequestVersions.get(key) === requestVersion) {
        this.toolCache = { ...this.toolCache, [key]: { status: 'ready', tools } };
      }
    } catch (error) {
      if (!(error instanceof BrowserRequestError)) throw error;
      if (this.toolRequestVersions.get(key) === requestVersion) {
        this.toolCache = { ...this.toolCache, [key]: { status: 'failed', tools: [] } };
      }
    }
  };

  retry = (connector: OpenApiConnectorListItem): void => {
    void this.load(connector, true);
  };

  setActivation = (connector: OpenApiConnectorListItem, operationId: string, activationStatus: OpenApiToolActivationStatus): void => {
    const key = this.cacheKey(connector);
    const current = this.toolCache[key];
    if (current === undefined) return;
    this.toolCache = {
      ...this.toolCache,
      [key]: { ...current, tools: current.tools.map((tool) => tool.operationId === operationId ? { ...tool, activationStatus } : tool) }
    };
  };

  private cacheKey = (connector: OpenApiConnectorListItem): string => {
    const authoritativeConnector = this.detailAccess.readDetail(connector.id) ?? connector;
    return `${authoritativeConnector.id}:${authoritativeConnector.updatedAt}`;
  };
}
