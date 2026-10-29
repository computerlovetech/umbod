import { SvelteMap } from 'svelte/reactivity';
import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';
import type { FilesApi } from '../api';
import type { NodeSummary } from '../domain/schemas';

export class DeletionState {
  available = $state(false);
  confirmation = $state.raw<NodeSummary | undefined>(undefined);

  get pending(): boolean {
    return this.target !== undefined && this.operations.has(this.target.id);
  }
  message = $state('');
  signInRequired = $state(false);
  needsReload = $state(false);
  mutationSucceeded = $state(false);
  private deletedParent: string | undefined;
  private target = $state.raw<NodeSummary | undefined>(undefined);
  private generation = 0;
  private controller: AbortController | undefined;
  private disposed = false;

  constructor(private readonly api: FilesApi, private readonly openParent: (id: string) => Promise<void>, private readonly reloadFile: () => Promise<void>, private readonly onDeleted: (node: NodeSummary) => void = () => {}, private readonly allowEligibilityWhilePending: boolean = true, private readonly operations = new SvelteMap<string, symbol>()) {}

  reset = (): void => {
    ++this.generation;
    this.controller?.abort();
    this.target = undefined;
    this.confirmation = undefined;
    this.available = false;
    this.message = '';
    this.signInRequired = false;
    this.needsReload = false;
    this.mutationSucceeded = false;
    this.deletedParent = undefined;
  };

  select = async (node: NodeSummary): Promise<void> => {
    this.reset();
    if (this.disposed || node.kind !== 'file' || typeof node.parent_id !== 'string') return;
    this.target = node;
    const generation = this.generation;
    this.controller = new AbortController();
    try {
      await this.api.filesystem.checkDeleteEligibility(node.id, this.controller.signal);
      if (this.disposed || generation !== this.generation) return;
      this.available = this.allowEligibilityWhilePending || !this.pending;
      if (!this.allowEligibilityWhilePending && this.pending) this.needsReload = true;
    } catch (error) {
      if (this.disposed || generation !== this.generation) return;
      this.signInRequired = error instanceof AuthenticationRequiredError;
      if (this.signInRequired || (error instanceof HttpError && [403, 409, 404].includes(error.status))) return;
      this.message = "Couldn't check deletion availability. Reload this file to try again.";
      this.needsReload = true;
    }
  };

  show = (): void => {
    if (!this.available || this.pending || this.needsReload || !this.target) return;
    this.confirmation = { ...this.target };
  };

  cancel = (): void => { this.confirmation = undefined; };

  confirm = async (): Promise<void> => {
    const target = this.confirmation;
    if (!target || !this.available || this.pending || this.disposed) return;
    const generation = this.generation;
    this.confirmation = undefined;
    this.available = false;
    const operation = Symbol(target.id);
    this.operations.set(target.id, operation);
    try {
      await this.api.filesystem.deleteFile(target.id, target.revision);
      if (!this.disposed) this.onDeleted(target);
      if (this.disposed || generation !== this.generation) return;
      this.mutationSucceeded = true;
      this.deletedParent = typeof target.parent_id === 'string' ? target.parent_id : undefined;
    } catch (error) {
      if (this.disposed || generation !== this.generation) return;
      this.needsReload = true;
      this.signInRequired = error instanceof AuthenticationRequiredError;
      this.message = this.signInRequired ? 'Sign in, then reload to check this file.'
        : error instanceof HttpError && error.status === 412 ? 'This file changed. Reload and review it before deleting.'
        : error instanceof HttpError && error.status === 403 ? 'This file is unavailable or you no longer have permission to delete it. Reload to check.'
        : error instanceof HttpError && error.status === 409 ? 'Only files can be deleted. Reload to check this location.'
        : "Couldn't confirm deletion. Reload to check whether this file still exists before trying again.";
    } finally {
      if (this.operations.get(target.id) === operation) this.operations.delete(target.id);
    }
    if (this.disposed || generation !== this.generation || !this.mutationSucceeded || !this.deletedParent) return;
    try {
      await this.openParent(this.deletedParent);
    } catch {
      if (this.disposed || generation !== this.generation) return;
      this.message = 'File deleted. Could not open the parent folder. Reload the parent folder to check its contents.';
      this.needsReload = true;
    }
  };

  reconcile = async (): Promise<void> => {
    if (!this.needsReload || this.pending || this.disposed) return;
    if (this.mutationSucceeded && this.deletedParent) {
      try { await this.openParent(this.deletedParent); } catch { return; }
    } else await this.reloadFile();
  };

  dispose = (): void => {
    this.disposed = true;
    this.reset();
  };
}
