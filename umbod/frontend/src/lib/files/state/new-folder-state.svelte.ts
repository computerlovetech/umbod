import type { FilesApi } from '../api';
import { createFolderSchema } from '../domain/schemas';
import { folderFailure } from '../errors';
import type { FilesState } from './files-state.svelte';

export class NewFolderState {
  open = $state(false);
  name = $state('');
  error = $state('');
  pending = $state(false);
  uncertain = $state(false);
  private readonly blockedParents = new Set<string>();
  private readonly pendingParents = new Set<string>();
  private parentId: string | undefined;
  private generation = 0;
  private disposed = false;

  constructor(private readonly api: FilesApi, private readonly files: FilesState) {}

  navigate = (): void => {
    ++this.generation;
    this.open = false;
    this.name = '';
    this.error = '';
    this.parentId = undefined;
    this.pending = false;
    this.uncertain = false;
  };

  show = (): void => {
    const target = this.files.creationTarget();
    if (!target || this.disposed) return;
    this.parentId = target.parentId;
    this.pending = this.pendingParents.has(target.parentId);
    this.uncertain = this.blockedParents.has(target.parentId);
    this.error = this.uncertain ? 'Reload this folder before trying again.' : '';
    this.open = true;
  };

  changeName = (name: string): void => {
    if (!this.pending) this.name = name;
  };

  cancel = (): void => {
    if (!this.pending) this.open = false;
  };

  reload = async (): Promise<void> => {
    const parentId = this.files.node?.id;
    this.navigate();
    await this.files.reload();
    if (parentId && this.files.node?.id === parentId && this.files.phase === 'ready') this.blockedParents.delete(parentId);
  };

  submit = async (): Promise<void> => {
    const target = this.files.creationTarget();
    if (this.disposed || !this.open || !target || this.parentId !== target.parentId || this.pendingParents.has(target.parentId) || this.blockedParents.has(target.parentId)) return;
    const parsed = createFolderSchema.safeParse({ name: this.name, metadata: { content_type: {}, attributes: {} } });
    if (!parsed.success) {
      this.error = 'Enter a folder name without path separators.';
      return;
    }
    const generation = this.generation;
    this.pendingParents.add(target.parentId);
    this.pending = true;
    this.error = '';
    try {
      const node = await this.api.filesystem.createFolder(target.parentId, parsed.data);
      if (!this.disposed) await this.files.acceptCreated(target.parentId, target.generation, node);
      if (this.disposed || generation !== this.generation) return;
      this.name = '';
      this.open = false;
    } catch (error) {
      const failure = folderFailure(error);
      if (failure.uncertain) {
        this.blockedParents.add(target.parentId);
        if (this.parentId === target.parentId && !this.disposed) this.uncertain = true;
      }
      if (this.disposed || generation !== this.generation) return;
      this.error = failure.message;
      this.uncertain = failure.uncertain;
    } finally {
      this.pendingParents.delete(target.parentId);
      if (!this.disposed && this.parentId === target.parentId) this.pending = false;
    }
  };

  dispose = (): void => {
    this.disposed = true;
    ++this.generation;
  };
}
