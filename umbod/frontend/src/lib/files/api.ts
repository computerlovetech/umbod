import type { CreateFolder, FileUpload, NodeSummary, UploadPolicy } from './domain/schemas';

export interface FilesystemApi {
  getRoot(signal?: AbortSignal): Promise<NodeSummary>;
  getNode(id: string, signal?: AbortSignal): Promise<NodeSummary>;
  listChildren(parentId: string, signal?: AbortSignal): Promise<NodeSummary[]>;
  createFolder(parentId: string, input: CreateFolder): Promise<NodeSummary>;
  getUploadPolicy(parentId: string, signal?: AbortSignal): Promise<UploadPolicy>;
  uploadFile(parentId: string, input: FileUpload): Promise<NodeSummary>;
}

export interface FilesApi {
  readonly filesystem: FilesystemApi;
}
