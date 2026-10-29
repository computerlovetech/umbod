import { SchemaValidationError, type Transport } from '$lib/admin/infrastructure/transport';
import { UploadPhaseError } from '../errors';
import type { FilesystemApi, UploadTransferPort } from '../api';
import { breadcrumbsSchema, type Breadcrumbs, deleteEligibilitySchema, fileRevisionSchema, childrenSchema, createFolderSchema, fileUploadSchema, nodeIdSchema, nodeSummarySchema, uploadEligibilitySchema, beginUploadSchema, uploadSessionSchema, type BeginUpload, type UploadSession, type CreateFolder, type FileUpload, type NodeSummary } from '../domain/schemas';

export class FilesystemRoute implements FilesystemApi {
  constructor(private readonly transport: Transport, private readonly transfer: UploadTransferPort) {}

  getRoot = (signal?: AbortSignal): Promise<NodeSummary> =>
    this.transport.request({ method: 'GET', path: '/me/filesystem/root', outputSchema: nodeSummarySchema, signal });

  getNode = (id: string, signal?: AbortSignal): Promise<NodeSummary> =>
    this.transport.request({ method: 'GET', path: this.nodePath(id), outputSchema: nodeSummarySchema, signal });

  getBreadcrumbs = (id: string, signal?: AbortSignal): Promise<Breadcrumbs> =>
    this.transport.request({ method: 'GET', path: this.nodePath(id) + '/breadcrumbs', outputSchema: breadcrumbsSchema, signal });

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

  checkDeleteEligibility = (id: string, signal?: AbortSignal): Promise<void> =>
    this.transport.request({
      method: 'OPTIONS', path: this.nodePath(id), outputSchema: deleteEligibilitySchema, responseBody: 'headers', signal
    });

  deleteFile = (id: string, revision: number): Promise<void> => {
    const parsed = fileRevisionSchema.safeParse(revision);
    if (!parsed.success) throw new SchemaValidationError('outbound', parsed.error.issues);
    return this.transport.request({ method: 'DELETE', path: this.nodePath(id), redirect: 'error', conditionalHeaders: { 'If-Match': `"${parsed.data}"` } });
  };

  checkUploadEligibility = (parentId: string, signal?: AbortSignal): Promise<void> =>
    this.transport.request({
      method: 'OPTIONS', path: this.nodePath(parentId) + '/uploads', outputSchema: uploadEligibilitySchema, responseBody: 'headers', signal
    });

  beginUpload = (parentId: string, input: BeginUpload): Promise<UploadSession> =>
    this.transport.request({
      method: 'POST', path: this.nodePath(parentId) + '/uploads', body: input,
      inputSchema: beginUploadSchema, outputSchema: uploadSessionSchema, redirect: 'error'
    });

  getUpload = (id: string): Promise<UploadSession> =>
    this.transport.request({ method: 'GET', path: '/me/filesystem/uploads/' + nodeIdSchema.parse(id), outputSchema: uploadSessionSchema, redirect: 'error' });

  transferUpload = async (session: UploadSession, file: File): Promise<void> => {
    const parsed = uploadSessionSchema.parse(session);
    await this.transfer.transfer(parsed.transfer, file, parsed.id);
  };

  completeUpload = (session: UploadSession): Promise<NodeSummary> => {
    const parsed = uploadSessionSchema.parse(session);
    return this.transport.request({
      method: 'POST', path: parsed.complete_url, apiEndpoint: { method: 'POST', path: `/me/filesystem/uploads/${parsed.id}/complete` },
      outputSchema: nodeSummarySchema, redirect: 'error'
    });
  };

  uploadFile = async (parentId: string, input: FileUpload): Promise<NodeSummary> => {
    const parsed = fileUploadSchema.safeParse(input);
    if (!parsed.success) throw new SchemaValidationError('outbound', parsed.error.issues);
    let session: UploadSession;
    try {
      session = await this.beginUpload(parentId, {
        name: parsed.data.name,
        metadata: { content_type: parsed.data.file.type || 'application/octet-stream', attributes: {} },
        size_bytes: parsed.data.file.size
      });
    } catch (cause) {
      throw new UploadPhaseError('begin', cause);
    }
    try {
      await this.transferUpload(session, parsed.data.file);
    } catch (cause) {
      throw new UploadPhaseError('transfer', cause);
    }
    try {
      return await this.completeUpload(session);
    } catch (cause) {
      throw new UploadPhaseError('complete', cause);
    }
  };

  private nodePath(id: string): string {
    return '/me/filesystem/nodes/' + nodeIdSchema.parse(id);
  }
}
