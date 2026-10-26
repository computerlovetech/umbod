import { nodeSummarySchema, type NodeSummary } from './domain/schemas';

export const rootId = '00000000-0000-4000-8000-000000000001';
export const folderId = '00000000-0000-4000-8000-000000000002';
export const fileId = '00000000-0000-4000-8000-000000000003';

export function filesystemNode(overrides: Partial<NodeSummary> = {}): NodeSummary {
  return nodeSummarySchema.parse({
    id: rootId, parent_id: {}, name: '', kind: 'directory',
    metadata: { content_type: {}, attributes: {} },
    created_at: '2026-01-01T10:00:00Z', updated_at: '2026-01-02T10:00:00Z', revision: 1,
    ...overrides
  });
}

export const filesystemFixture: NodeSummary[] = [
  filesystemNode(),
  filesystemNode({ id: folderId, parent_id: rootId, name: 'Projects' }),
  filesystemNode({ id: fileId, parent_id: folderId, name: 'Notes.txt', kind: 'file', metadata: { content_type: 'text/plain', attributes: { topic: 'Planning' } } })
];

export interface Deferred<T> {
  promise: Promise<T>;
  resolve(value: T): void;
  reject(error: unknown): void;
}

export function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((complete, fail) => { resolve = complete; reject = fail; });
  return { promise, resolve, reject };
}
