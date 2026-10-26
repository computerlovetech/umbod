import type { Transport } from '$lib/admin/infrastructure/transport';
import type { FilesystemApi } from '../api';
import { childrenSchema, createFolderSchema, nodeIdSchema, nodeSummarySchema, type CreateFolder, type NodeSummary } from '../domain/schemas';

export class FilesystemRoute implements FilesystemApi {
  constructor(private readonly transport: Transport) {}

  getRoot = (signal?: AbortSignal): Promise<NodeSummary> =>
    this.transport.request({ method: 'GET', path: '/me/filesystem/root', outputSchema: nodeSummarySchema, signal });

  getNode = (id: string, signal?: AbortSignal): Promise<NodeSummary> =>
    this.transport.request({ method: 'GET', path: this.nodePath(id), outputSchema: nodeSummarySchema, signal });

  listChildren = async (parentId: string, signal?: AbortSignal): Promise<NodeSummary[]> => {
    const result = await this.transport.request({
      method: 'GET', path: this.nodePath(parentId) + '/children', outputSchema: childrenSchema, signal
    });
    return result.nodes;
  };

  createFolder = (parentId: string, input: CreateFolder): Promise<NodeSummary> =>
    this.transport.request({
      method: 'POST', path: this.nodePath(parentId) + '/directories',
      body: input, inputSchema: createFolderSchema, outputSchema: nodeSummarySchema
    });

  private nodePath(id: string): string {
    return '/me/filesystem/nodes/' + nodeIdSchema.parse(id);
  }
}
