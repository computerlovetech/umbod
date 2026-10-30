import type { Breadcrumbs, CreateFolder, FileUpload, NodeSummary, BeginUpload, UploadSession, UploadTransfer } from './domain/schemas';

export interface FilesystemApi {
  getRoot(signal?: AbortSignal): Promise<NodeSummary>;
  getNode(id: string, signal?: AbortSignal): Promise<NodeSummary>;
  getBreadcrumbs(id: string, signal?: AbortSignal): Promise<Breadcrumbs>;
  listChildren(parentId: string, signal?: AbortSignal): Promise<NodeSummary[]>;
  createFolder(parentId: string, input: CreateFolder): Promise<NodeSummary>;
  checkDeleteEligibility(id: string, signal?: AbortSignal): Promise<void>;
  deleteFile(id: string, revision: number): Promise<void>;
  checkUploadEligibility(parentId: string, signal?: AbortSignal): Promise<void>;
  beginUpload(parentId: string, input: BeginUpload): Promise<UploadSession>;
  getUpload(id: string): Promise<UploadSession>;
  transferUpload(session: UploadSession, file: File): Promise<void>;
  completeUpload(session: UploadSession): Promise<NodeSummary>;
  uploadFile(parentId: string, input: FileUpload): Promise<NodeSummary>;
}

export interface UploadTransferPort {
  transfer(descriptor: UploadTransfer, file: File, sessionId: string): Promise<void>;
}

export interface NodeSharingApi {
  inspectAccess(id: string, signal?: AbortSignal): Promise<import('./domain/sharing').NodeAccess>;
  replaceAccess(id: string, revision: string, body: import('./domain/sharing').ReplaceAccess): Promise<import('./domain/sharing').NodeAccess>;
  listEligibleSharingGroups(id: string, signal?: AbortSignal): Promise<import('./domain/sharing').SharingGroup[]>;
}

export interface FilesApi {
  readonly filesystem: FilesystemApi;
  readonly sharing: NodeSharingApi;
}
