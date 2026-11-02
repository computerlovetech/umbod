import { InMemoryNodeSharing } from './in-memory-sharing.test-support';
import type { FilesApi, FilesystemApi } from '../api';
import { browseResultSchema, type BrowseResult, updateNodeSchema, type UpdateNode, updateDescriptionSchema, type UpdateDescription, breadcrumbsSchema, type Breadcrumbs, type BreadcrumbItem, fileRevisionSchema, createFolderSchema, fileUploadSchema, nodeIdSchema, nodeSummarySchema, beginUploadSchema, uploadSessionSchema, rawUploadSchema, type BeginUpload, type UploadSession, type CreateFolder, type FileUpload, type NodeSummary } from '../domain/schemas';
import { UploadPhaseError } from '../errors';
import { HttpError } from '$lib/admin/infrastructure/transport';

export class InMemoryFilesystem implements FilesystemApi {
  private readonly nodes = new Map<string, NodeSummary>();
  private readonly sessions = new Map<string, { session: UploadSession; parentId: string; input: BeginUpload; bytes: Uint8Array | undefined; node: NodeSummary | undefined }>();
  private readonly content = new Map<string, Uint8Array>();

  constructor(private readonly rootId: string, nodes: NodeSummary[], private readonly uploadLimitBytes?: number, private readonly canDelete: (node: NodeSummary) => boolean = () => true, private readonly canRead: (node: NodeSummary) => boolean = () => true, private readonly canWrite: (node: NodeSummary) => boolean = () => true, private readonly canShare: (id: string) => boolean = () => false) {
    nodeIdSchema.parse(rootId);
    for (const node of nodes) this.nodes.set(node.id, nodeSummarySchema.parse(node));
  }

  browse = async (target: string | null, signal?: AbortSignal): Promise<BrowseResult> => {
    const node = await this.getNode(target ?? this.rootId, signal);
    const breadcrumbs = await this.getBreadcrumbs(node.id, signal);
    const entries = node.kind === 'directory' ? await this.listChildren(node.id, signal) : [];
    signal?.throwIfAborted();
    return browseResultSchema.parse({
      node, breadcrumbs, entries, truncated: false,
      capabilities: [node, ...entries].map((entry) => {
        const writable = this.canWrite(entry);
        const parent = typeof entry.parent_id === 'string' ? this.nodes.get(entry.parent_id) : undefined;
        return {
          node_id: entry.id,
          rename: writable && !!parent,
          move: writable && !!parent && this.canWrite(parent),
          edit_description: writable,
          delete: entry.kind === 'file' && !!parent && this.canDelete(entry),
          share: this.canShare(entry.id),
          upload: entry.kind === 'directory' && writable,
          create_directory: entry.kind === 'directory' && writable
        };
      })
    });
  };

  getNode = async (id: string, signal?: AbortSignal): Promise<NodeSummary> => {
    signal?.throwIfAborted();
    const node = this.nodes.get(nodeIdSchema.parse(id));
    if (!node) throw new HttpError(404, 'Not found', {});
    if (!this.canRead(node)) throw new HttpError(403, 'Forbidden', {});
    return nodeSummarySchema.parse(node);
  };

  getBreadcrumbs = async (id: string, signal?: AbortSignal): Promise<Breadcrumbs> => {
    signal?.throwIfAborted();
    let node = this.nodes.get(nodeIdSchema.parse(id));
    if (!node || !this.canRead(node)) throw new HttpError(403, 'Forbidden', {});
    const items: BreadcrumbItem[] = [];
    const seen = new Set<string>();
    while (node) {
      signal?.throwIfAborted();
      if (seen.has(node.id)) throw new Error('Unable to load path');
      seen.add(node.id);
      items.unshift({ id: node.id, name: node.name, kind: node.kind });
      if (node.id === this.rootId) return breadcrumbsSchema.parse({ items, complete: true });
      const parent: NodeSummary | undefined = typeof node.parent_id === 'string' ? this.nodes.get(node.parent_id) : undefined;
      if (!parent || !this.canRead(parent)) return breadcrumbsSchema.parse({ items, complete: false });
      if (parent.kind !== 'directory') throw new Error('Unable to load path');
      node = parent;
    }
    throw new Error('Unable to load path');
  };

  listChildren = async (parentId: string, signal?: AbortSignal): Promise<NodeSummary[]> => {
    const parent = await this.getNode(parentId, signal);
    signal?.throwIfAborted();
    if (parent.kind !== 'directory') throw new HttpError(400, 'Not a directory', {});
    return Array.from(this.nodes.values()).filter((node) => node.parent_id === parentId && this.canRead(node)).map((node) => nodeSummarySchema.parse(node));
  };

  checkDescriptionEligibility = (id: string, signal?: AbortSignal): Promise<void> => this.checkUpdateEligibility(id, signal);

  checkUpdateEligibility = async (id: string, signal?: AbortSignal): Promise<void> => {
    signal?.throwIfAborted();
    const node = this.nodes.get(nodeIdSchema.parse(id));
    if (!node || !this.canRead(node) || !this.canWrite(node)) throw new HttpError(403, 'Forbidden', {});
  };

  updateDescription = async (id: string, revision: number, input: UpdateDescription): Promise<NodeSummary> => {
    const body = updateDescriptionSchema.parse(input);
    return this.updateNode(id, revision, { metadata: { attributes: { description: body.description } } });
  };

  updateNode = async (id: string, revision: number, input: UpdateNode): Promise<NodeSummary> => {
    const body = updateNodeSchema.parse(input);
    const expected = fileRevisionSchema.parse(revision);
    await this.checkUpdateEligibility(id);
    const node = this.nodes.get(id);
    if (!node || !this.canRead(node) || !this.canWrite(node)) throw new HttpError(403, 'Forbidden', {});
    if (node.revision !== expected) throw new HttpError(412, 'Stale revision', {});
    if ((body.name !== undefined || body.parent_id !== undefined) && id === this.rootId) throw new HttpError(409, 'Root cannot change location', {});
    if (body.parent_id !== undefined) {
      if (typeof node.parent_id !== 'string') throw new HttpError(409, 'Missing parent', {});
      await this.checkUpdateEligibility(node.parent_id);
      await this.checkUpdateEligibility(body.parent_id);
      if (this.nodes.get(body.parent_id)?.kind !== 'directory') throw new HttpError(409, 'Not a directory', {});
      let ancestor = this.nodes.get(body.parent_id);
      const seen = new Set<string>();
      while (ancestor) {
        if (ancestor.id === id || seen.has(ancestor.id)) throw new HttpError(409, 'Cycle', {});
        seen.add(ancestor.id);
        ancestor = typeof ancestor.parent_id === 'string' ? this.nodes.get(ancestor.parent_id) : undefined;
      }
    }
    if (this.nodes.get(id)?.revision !== expected) throw new HttpError(412, 'Stale revision', {});
    const name = body.name ?? node.name;
    const parent_id = body.parent_id ?? node.parent_id;
    if (Array.from(this.nodes.values()).some((other) => other.id !== id && other.parent_id === parent_id && other.name === name)) throw new HttpError(409, 'Name collision', {});
    const attributes = { ...node.metadata.attributes };
    for (const [key, value] of Object.entries(body.metadata?.attributes ?? {})) {
      if (value) attributes[key] = value;
      else delete attributes[key];
    }
    const updated = nodeSummarySchema.parse({ ...node, name, parent_id, metadata: { content_type: body.metadata?.content_type ?? node.metadata.content_type, attributes }, revision: node.revision + 1, updated_at: new Date().toISOString() });
    this.nodes.set(id, updated);
    return nodeSummarySchema.parse(updated);
  };

  checkDeleteEligibility = async (id: string, signal?: AbortSignal): Promise<void> => {
    signal?.throwIfAborted();
    const node = this.nodes.get(nodeIdSchema.parse(id));
    if (!node || !this.canRead(node) || !this.canDelete(node) || node.kind !== 'file' || id === this.rootId) throw new HttpError(403, 'Forbidden', {});
  };

  deleteFile = async (id: string, revision: number): Promise<void> => {
    const expected = fileRevisionSchema.parse(revision);
    const node = this.nodes.get(nodeIdSchema.parse(id));
    if (!node || !this.canRead(node) || !this.canDelete(node)) throw new HttpError(403, 'Forbidden', {});
    if (node.kind !== 'file' || id === this.rootId) throw new HttpError(409, 'Not a file', {});
    if (node.revision !== expected) throw new HttpError(412, 'Stale revision', {});
    this.nodes.delete(id);
  };

  beginUpload = async (parentId: string, input: BeginUpload): Promise<UploadSession> => {
    const body = beginUploadSchema.parse(input);
    const parent = await this.getNode(parentId);
    if (parent.kind !== 'directory' || !this.canWrite(parent)) throw new HttpError(403, 'Forbidden', {});
    if (this.uploadLimitBytes !== undefined && body.size_bytes > this.uploadLimitBytes) throw new HttpError(413, 'File too large', {});
    const children = await this.listChildren(parentId);
    if (children.some((node) => node.name === body.name)) throw new HttpError(409, 'Conflict', { detail: { code: 'filesystem_name_collision' } });
    const id = crypto.randomUUID();
    const session = uploadSessionSchema.parse({
      id, expires_at: new Date(Date.now() + 3600000).toISOString(), status: 'pending',
      transfer: { type: 'single', method: 'PUT', url: '/api/me/filesystem/uploads/' + id + '/content',
        headers: { 'Content-Type': body.metadata.content_type }, authorization: { type: 'same_origin' } },
      complete_url: '/api/me/filesystem/uploads/' + id + '/complete'
    });
    this.sessions.set(id, { session, parentId, input: body, bytes: undefined, node: undefined });
    return uploadSessionSchema.parse(session);
  };

  transferUpload = async (session: UploadSession, file: File): Promise<void> => {
    const record = this.uploadRecord(uploadSessionSchema.parse(session).id);
    const body = rawUploadSchema.parse(file);
    if (record.session.status !== 'pending' || body.size !== record.input.size_bytes) throw new HttpError(409, 'Invalid upload', {});
    record.bytes = new Uint8Array(await body.arrayBuffer());
    record.session = { ...record.session, status: 'uploaded' };
  };

  completeUpload = async (session: UploadSession): Promise<NodeSummary> => {
    const record = this.uploadRecord(uploadSessionSchema.parse(session).id);
    if (record.node) {
      if (!this.nodes.has(record.node.id)) throw new HttpError(403, 'Forbidden', {});
      return nodeSummarySchema.parse(record.node);
    }
    if (record.bytes === undefined) throw new HttpError(409, 'Content missing', {});
    const children = await this.listChildren(record.parentId);
    if (children.some((node) => node.name === record.input.name)) throw new HttpError(409, 'Conflict', { detail: { code: 'filesystem_name_collision' } });
    const timestamp = new Date().toISOString();
    const node = nodeSummarySchema.parse({
      id: crypto.randomUUID(), parent_id: record.parentId, name: record.input.name, kind: 'file',
      metadata: record.input.metadata, created_at: timestamp, updated_at: timestamp, revision: 1
    });
    this.nodes.set(node.id, node);
    this.content.set(node.id, record.bytes);
    record.node = node;
    record.session = { ...record.session, status: 'completed' };
    return nodeSummarySchema.parse(node);
  };

  readContent = async (id: string): Promise<Uint8Array> => {
    await this.getNode(id);
    const bytes = this.content.get(id);
    if (!bytes) throw new HttpError(404, 'Content missing', {});
    return bytes.slice();
  };

  private uploadRecord(id: string): { session: UploadSession; parentId: string; input: BeginUpload; bytes: Uint8Array | undefined; node: NodeSummary | undefined } {
    const record = this.sessions.get(nodeIdSchema.parse(id));
    if (!record) throw new HttpError(404, 'Upload missing', {});
    return record;
  }

  uploadFile = async (parentId: string, input: FileUpload): Promise<NodeSummary> => {
    const body = fileUploadSchema.parse(input);
    let session: UploadSession;
    try {
      session = await this.beginUpload(parentId, {
        name: body.name, metadata: { content_type: body.file.type || 'application/octet-stream', attributes: body.description ? { description: body.description } : {} }, size_bytes: body.file.size
      });
    } catch (cause) {
      throw new UploadPhaseError('begin', cause);
    }
    try {
      await this.transferUpload(session, body.file);
    } catch (cause) {
      throw new UploadPhaseError('transfer', cause);
    }
    try {
      return await this.completeUpload(session);
    } catch (cause) {
      throw new UploadPhaseError('complete', cause);
    }
  };

  createFolder = async (parentId: string, input: CreateFolder): Promise<NodeSummary> => {
    const body = createFolderSchema.parse(input);
    const children = await this.listChildren(parentId);
    if (children.some((node) => node.name === body.name)) throw new HttpError(409, 'Conflict', { detail: { code: 'filesystem_name_collision' } });
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
  readonly sharing = new InMemoryNodeSharing();
  readonly filesystem: InMemoryFilesystem;

  constructor(rootId: string, nodes: NodeSummary[], uploadLimitBytes?: number, canDelete?: (node: NodeSummary) => boolean, canRead?: (node: NodeSummary) => boolean, canWrite?: (node: NodeSummary) => boolean) {
    this.filesystem = new InMemoryFilesystem(rootId, nodes, uploadLimitBytes, canDelete, canRead, canWrite, this.sharing.available);
  }
}
