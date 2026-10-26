import type { FilesApi, FilesystemApi } from '../api';
import { createFolderSchema, nodeIdSchema, nodeSummarySchema, type CreateFolder, type NodeSummary } from '../domain/schemas';
import { HttpError } from '$lib/admin/infrastructure/transport';

class InMemoryFilesystem implements FilesystemApi {
  private readonly nodes = new Map<string, NodeSummary>();

  constructor(private readonly rootId: string, nodes: NodeSummary[]) {
    for (const node of nodes) this.nodes.set(node.id, nodeSummarySchema.parse(node));
  }

  getRoot = async (): Promise<NodeSummary> => this.getNode(this.rootId);

  getNode = async (id: string): Promise<NodeSummary> => {
    const node = this.nodes.get(nodeIdSchema.parse(id));
    if (!node) throw new HttpError(404, 'Not found', {});
    return nodeSummarySchema.parse(node);
  };

  listChildren = async (parentId: string): Promise<NodeSummary[]> => {
    const parent = await this.getNode(parentId);
    if (parent.kind !== 'directory') throw new HttpError(400, 'Not a directory', {});
    return Array.from(this.nodes.values()).filter((node) => node.parent_id === parentId).map((node) => nodeSummarySchema.parse(node));
  };

  createFolder = async (parentId: string, input: CreateFolder): Promise<NodeSummary> => {
    const body = createFolderSchema.parse(input);
    const children = await this.listChildren(parentId);
    if (children.some((node) => node.name === body.name)) throw new HttpError(409, 'Conflict', {});
    const timestamp = new Date().toISOString();
    const node = nodeSummarySchema.parse({
      id: crypto.randomUUID(), parent_id: parentId, name: body.name, kind: 'directory',
      metadata: body.metadata, created_at: timestamp, updated_at: timestamp, revision: 1
    });
    this.nodes.set(node.id, node);
    return nodeSummarySchema.parse(node);
  };
}

export class InMemoryFilesApi implements FilesApi {
  readonly filesystem: FilesystemApi;

  constructor(rootId: string, nodes: NodeSummary[]) {
    this.filesystem = new InMemoryFilesystem(rootId, nodes);
  }
}
