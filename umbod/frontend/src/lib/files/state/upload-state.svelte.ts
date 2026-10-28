import { SvelteMap, SvelteSet } from 'svelte/reactivity';
import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';
import type { FilesApi } from '../api';
import { fileUploadSchema } from '../domain/schemas';
import { uploadFailure } from '../errors';
import type { FilesState } from './files-state.svelte';

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} ${bytes === 1 ? 'byte' : 'bytes'}`;
  if (bytes < 1048576) return `${Number((bytes / 1024).toFixed(1))} KiB`;
  return `${Number((bytes / 1048576).toFixed(1))} MiB`;
}

export class UploadState {
  open = $state(false);
  file = $state.raw<File | undefined>(undefined);
  name = $state('');
  error = $state('');
  status = $state('');
  pending = $state(false);
  uncertain = $state(false);
  signInRequired = $state(false);
  private parentId: string | undefined;
  private readonly pendingParents = new SvelteMap<string, { file: File; name: string }>();
  private readonly blockedParents = new SvelteSet<string>();
  private disposed = false;

  constructor(private readonly api: FilesApi, private readonly files: FilesState) {}

  get available(): boolean {
    return this.files.phase === 'ready' && this.files.node?.kind === 'directory' && this.files.uploadAvailability === 'allowed';
  }

  get canDrop(): boolean {
    const target = this.files.creationTarget();
    return !this.disposed && this.available && !this.open && !!target && !this.pendingParents.has(target.parentId) && !this.blockedParents.has(target.parentId);
  }

  drop = async (files: readonly File[]): Promise<void> => {
    if (!this.beginDrop()) return;
    if (files.length === 0) {
      this.rejectSelection('Choose one file to upload.');
      return;
    }
    this.select(files);
    await this.submit();
  };

  rejectDrop = (message: string): void => {
    if (this.beginDrop()) this.rejectSelection(message);
  };

  get maxBytes(): number {
    return this.files.uploadPolicy?.max_bytes ?? 0;
  }

  get canSubmit(): boolean {
    return this.available && !this.pending && !this.uncertain && !this.error && !this.signInRequired && !!this.file && this.file.size <= this.maxBytes && fileUploadSchema.safeParse({ file: this.file, name: this.name }).success;
  }

  navigate = (): void => {
    this.open = false;
    this.file = undefined;
    this.name = '';
    this.error = '';
    this.status = '';
    this.pending = false;
    this.uncertain = false;
    this.signInRequired = false;
    this.parentId = undefined;
  };

  show = (): void => {
    const target = this.files.creationTarget();
    if (this.disposed || !target || !this.available) return;
    this.parentId = target.parentId;
    const pending = this.pendingParents.get(target.parentId);
    this.pending = !!pending;
    if (pending) {
      this.file = pending.file;
      this.name = pending.name;
    }
    this.uncertain = this.blockedParents.has(target.parentId);
    this.error = this.uncertain ? 'An earlier upload could not be confirmed. Reload this folder before trying again.' : '';
    this.status = '';
    this.open = true;
  };

  select = (files: readonly File[]): void => {
    if (this.pending || this.uncertain || files.length === 0) return;
    if (files.length !== 1) {
      this.rejectSelection('Choose one file at a time. Multiple files were not selected.');
      return;
    }
    const file = files[0];
    if (file.size > this.maxBytes) {
      this.rejectSelection(`Choose a file no larger than ${formatFileSize(this.maxBytes)}. This file contains ${file.size.toLocaleString()} bytes.`);
      return;
    }
    const parsed = fileUploadSchema.safeParse({ file, name: file.name });
    if (!parsed.success) {
      this.rejectSelection('Choose a file with a name without path separators.');
      return;
    }
    this.file = file;
    this.name = file.name;
    this.error = '';
    this.status = `${file.name} selected, ${formatFileSize(file.size)}. Ready to upload.`;
  };

  rejectSelection = (message: string): void => {
    if (this.pending || this.uncertain) return;
    this.error = message;
    this.status = '';
  };

  changeName = (name: string): void => {
    if (this.pending || this.uncertain) return;
    this.name = name;
    this.error = '';
  };

  remove = (): void => {
    if (this.pending || this.uncertain) return;
    this.file = undefined;
    this.name = '';
    this.error = '';
    this.status = 'File removed. Choose another file.';
  };

  cancel = (): void => {
    if (this.pending) return;
    this.open = false;
    this.file = undefined;
    this.name = '';
    this.error = '';
    this.status = '';
  };

  reload = async (): Promise<void> => {
    if (this.pending) return;
    const parentId = this.files.node?.id;
    this.navigate();
    await this.files.reload();
    if (parentId && this.files.node?.id === parentId && this.files.phase === 'ready') this.blockedParents.delete(parentId);
  };

  submit = async (): Promise<void> => {
    const target = this.files.creationTarget();
    if (this.disposed || !this.open || !target || this.parentId !== target.parentId || !this.canSubmit || this.pendingParents.has(target.parentId) || this.blockedParents.has(target.parentId)) return;
    const input = fileUploadSchema.parse({ file: this.file, name: this.name });
    this.pendingParents.set(target.parentId, input);
    this.pending = true;
    this.error = '';
    this.status = '';
    try {
      const node = await this.api.filesystem.uploadFile(target.parentId, input);
      if (node.kind !== 'file' || node.parent_id !== target.parentId || node.name !== input.name) throw new Error('Unexpected upload result');
      if (!this.disposed) await this.files.acceptCreated(target.parentId, target.generation, node);
      if (this.disposed || this.parentId !== target.parentId) return;
      this.file = undefined;
      this.name = '';
      this.open = false;
      this.status = `${node.name} uploaded.`;
    } catch (error) {
      const failure = uploadFailure(error);
      if (failure.uncertain) this.blockedParents.add(target.parentId);
      if (this.disposed || this.parentId !== target.parentId) return;
      this.error = failure.message;
      this.uncertain = failure.uncertain;
      this.signInRequired = error instanceof AuthenticationRequiredError;
      if (this.signInRequired) this.files.rejectUploadAccess(target.parentId, 'sign-in');
      else if (error instanceof HttpError && error.status === 403) this.files.rejectUploadAccess(target.parentId, 'denied');
      else if (error instanceof HttpError && error.status === 413) void this.files.checkUploadAvailability();
    } finally {
      this.pendingParents.delete(target.parentId);
      if (!this.disposed && this.parentId === target.parentId) this.pending = false;
    }
  };

  private beginDrop(): boolean {
    if (!this.canDrop) return false;
    this.show();
    this.remove();
    return true;
  }

  dispose = (): void => {
    this.disposed = true;
    this.navigate();
  };
}
