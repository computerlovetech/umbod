import type { BrowseResult, UpdateNode, UpdateDescription, Breadcrumbs, CreateFolder, FileUpload, NodeSummary, BeginUpload, UploadSession, UploadTransfer } from './domain/schemas';

export interface FilesystemApi {
  browse(target: string | null, signal?: AbortSignal): Promise<BrowseResult>;
  getNode(id: string, signal?: AbortSignal): Promise<NodeSummary>;
  getBreadcrumbs(id: string, signal?: AbortSignal): Promise<Breadcrumbs>;
  listChildren(parentId: string, signal?: AbortSignal): Promise<NodeSummary[]>;
  createFolder(parentId: string, input: CreateFolder): Promise<NodeSummary>;
  checkUpdateEligibility(id: string, signal?: AbortSignal): Promise<void>;
  updateNode(id: string, revision: number, input: UpdateNode): Promise<NodeSummary>;
  checkDescriptionEligibility(id: string, signal?: AbortSignal): Promise<void>;
  updateDescription(id: string, revision: number, input: UpdateDescription): Promise<NodeSummary>;
  checkDeleteEligibility(id: string, signal?: AbortSignal): Promise<void>;
  deleteFile(id: string, revision: number): Promise<void>;
  beginUpload(parentId: string, input: BeginUpload): Promise<UploadSession>;
  transferUpload(session: UploadSession, file: File): Promise<void>;
  completeUpload(session: UploadSession): Promise<NodeSummary>;
  uploadFile(parentId: string, input: FileUpload): Promise<NodeSummary>;
}

export interface UploadTransferPort {
  transfer(descriptor: UploadTransfer, file: File, sessionId: string): Promise<void>;
}

export interface NodeSharingApi {
  inspectAccess(id: string, recipientType?: import('./domain/sharing').SharingRecipientType, signal?: AbortSignal): Promise<import('./domain/sharing').NodeAccess>;
  replaceAccess(id: string, revision: string, body: import('./domain/sharing').ReplaceAccess, recipientType: import('./domain/sharing').SharingRecipientType): Promise<import('./domain/sharing').NodeAccess>;
  listEligibleSharingGroups(id: string, signal?: AbortSignal): Promise<import('./domain/sharing').SharingGroup[]>;
}

export interface FilesApi {
  readonly filesystem: FilesystemApi;
  readonly sharing: NodeSharingApi;
}
