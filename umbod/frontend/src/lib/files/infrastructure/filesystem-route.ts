import { SchemaValidationError, type Transport } from '$lib/admin/infrastructure/transport';
import type { FilesystemApi } from '../api';
import { childrenSchema, createFolderSchema, fileUploadSchema, nodeIdSchema, nodeSummarySchema, uploadPolicySchema, type CreateFolder, type FileUpload, type NodeSummary, type UploadPolicy } from '../domain/schemas';

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

  getUploadPolicy = (parentId: string, signal?: AbortSignal): Promise<UploadPolicy> =>
    this.transport.request({
      method: 'GET', path: this.nodePath(parentId) + '/upload-policy', outputSchema: uploadPolicySchema, signal
    });

  uploadFile = async (parentId: string, input: FileUpload): Promise<NodeSummary> => {
    const parsed = fileUploadSchema.safeParse(input);
    if (!parsed.success) throw new SchemaValidationError('outbound', parsed.error.issues);
    const form = new FormData();
    form.append('file', parsed.data.file, parsed.data.file.name);
    form.append('name', parsed.data.name);
    return this.transport.request({
      method: 'POST', path: this.nodePath(parentId) + '/files',
      requestBody: { kind: 'multipart', form, metadata: input, metadataSchema: fileUploadSchema },
      outputSchema: nodeSummarySchema
    });
  };

  private nodePath(id: string): string {
    return '/me/filesystem/nodes/' + nodeIdSchema.parse(id);
  }
}
