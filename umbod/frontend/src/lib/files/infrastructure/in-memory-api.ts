import type { FilesApi, FilesystemApi } from '../api';
import { createFolderSchema, fileUploadSchema, nodeIdSchema, nodeSummarySchema, uploadPolicySchema, type CreateFolder, type FileUpload, type NodeSummary, type UploadPolicy } from '../domain/schemas';
import { HttpError } from '$lib/admin/infrastructure/transport';

class InMemoryFilesystem implements FilesystemApi {
  private readonly nodes = new Map<string, NodeSummary>();

  constructor(private readonly rootId: string, nodes: NodeSummary[], private readonly policy: UploadPolicy) {
    nodeIdSchema.parse(rootId);
    uploadPolicySchema.parse(policy);
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

  getUploadPolicy = async (parentId: string): Promise<UploadPolicy> => {
    const parent = await this.getNode(parentId);
    if (parent.kind !== 'directory') throw new HttpError(409, 'Not a directory', {});
    return uploadPolicySchema.parse(this.policy);
  };

  uploadFile = async (parentId: string, input: FileUpload): Promise<NodeSummary> => {
    const body = fileUploadSchema.parse(input);
    const policy = await this.getUploadPolicy(parentId);
    if (body.file.size > policy.max_bytes) throw new HttpError(413, 'File too large', {});
    const children = await this.listChildren(parentId);
    if (children.some((node) => node.name === body.name)) throw new HttpError(409, 'Conflict', {});
    const timestamp = new Date().toISOString();
    const node = nodeSummarySchema.parse({
      id: crypto.randomUUID(), parent_id: parentId, name: body.name, kind: 'file',
      metadata: { content_type: body.file.type || 'application/octet-stream', attributes: {} },
      created_at: timestamp, updated_at: timestamp, revision: 1
    });
    this.nodes.set(node.id, node);
    return nodeSummarySchema.parse(node);
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

  constructor(rootId: string, nodes: NodeSummary[], policy: UploadPolicy = { max_bytes: 10485760 }) {
    this.filesystem = new InMemoryFilesystem(rootId, nodes, uploadPolicySchema.parse(policy));
  }
}
