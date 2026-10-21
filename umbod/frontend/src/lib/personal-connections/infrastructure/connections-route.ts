import type { Transport } from '$lib/admin/infrastructure/transport';
import type { ConnectionsPort } from '../api';
import { emptyRequestSchema, enablementRequestSchema, selectionListSchema, selectionSchema, type EmptyRequest, type EnablementRequest, type Selection, type SelectionList } from '../domain/schemas';

export function connectionPath(id: string): string {
  return `/me/connectors/mcp/${encodeURIComponent(id)}`;
}

export class ConnectionsRoute implements ConnectionsPort {
  constructor(private readonly transport: Transport) {}
  list = (): Promise<SelectionList> => this.transport.request({ method: 'GET', path: '/me/connectors/mcp', outputSchema: selectionListSchema });
  get = (id: string): Promise<Selection> => this.transport.request({ method: 'GET', path: connectionPath(id), outputSchema: selectionSchema });
  setEnablement = (id: string, body: EnablementRequest): Promise<Selection> => this.transport.request({
    method: 'PUT', path: `${connectionPath(id)}/enablement`, body, inputSchema: enablementRequestSchema, outputSchema: selectionSchema
  });
  disconnect = (id: string): Promise<void> => this.transport.request<void>({ method: 'DELETE', path: `${connectionPath(id)}/authorization` });
  discover = (id: string, body: EmptyRequest): Promise<void> => this.transport.request<void>({
    method: 'POST', path: `${connectionPath(id)}/tools/discovery`, body, inputSchema: emptyRequestSchema
  });
}
