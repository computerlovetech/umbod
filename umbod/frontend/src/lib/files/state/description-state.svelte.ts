import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';
import type { FilesystemApi } from '../api';
import { nodeSummarySchema, type NodeSummary } from '../domain/schemas';

export class DescriptionState {
  private current = $state.raw<NodeSummary | undefined>(undefined);
  private availability = $state<'hidden' | 'loading' | 'allowed' | 'denied' | 'error' | 'sign-in'>('hidden');
  private editing = $state(false);
  private value = $state('');
  private saving = $state(false);
  private message = $state('');
  private notice = $state('');
  private conflict = $state(false);
  private generation = 0;
  private disposed = false;
  private controller: AbortController | undefined;
  private readonly pendingIds = new Set<string>();

  constructor(private readonly api: FilesystemApi, private readonly accept: (node: NodeSummary) => void, private readonly reloadNode: () => Promise<void>) {}

  get description(): string { return this.current?.metadata.attributes.description ?? ''; }
  get available(): boolean { return this.availability === 'allowed'; }
  get eligibility(): string { return this.availability; }
  get open(): boolean { return this.editing; }
  get draft(): string { return this.value; }
  get pending(): boolean { return this.saving; }
  get error(): string { return this.message; }
  get status(): string { return this.notice; }
  get needsReload(): boolean { return this.conflict; }
  get canSave(): boolean { return this.available && this.editing && !this.saving && !this.conflict && !!this.current && !this.pendingIds.has(this.current.id); }

  reset = (): void => {
    ++this.generation;
    this.controller?.abort();
    this.current = undefined;
    this.availability = 'hidden';
    this.editing = false;
    this.value = '';
    this.saving = false;
    this.message = '';
    this.notice = '';
    this.conflict = false;
  };

  select = async (node: NodeSummary, allowed?: boolean): Promise<void> => {
    if (this.disposed) return;
    this.reset();
    this.current = node;
    if (allowed !== undefined) {
      this.availability = allowed ? 'allowed' : 'denied';
      return;
    }
    await this.checkEligibility();
  };

  checkEligibility = async (): Promise<void> => {
    const node = this.current;
    if (!node || this.disposed) return;
    const generation = ++this.generation;
    this.controller?.abort();
    this.controller = new AbortController();
    this.availability = 'loading';
    try {
      await this.api.checkDescriptionEligibility(node.id, this.controller.signal);
      if (this.disposed || generation !== this.generation) return;
      this.availability = 'allowed';
    } catch (error) {
      if (this.disposed || generation !== this.generation) return;
      this.availability = error instanceof AuthenticationRequiredError ? 'sign-in' : error instanceof HttpError && [403, 404].includes(error.status) ? 'denied' : 'error';
    }
  };

  acceptUpdatedNode = (node: NodeSummary): void => {
    if (this.current?.id === node.id && node.revision >= this.current.revision) this.current = node;
  };

  show = (): void => {
    if (!this.available || this.disposed || !this.current || this.pendingIds.has(this.current.id)) return;
    this.value = this.description;
    this.message = '';
    this.notice = '';
    this.editing = true;
  };

  change = (value: string): void => { if (this.editing && !this.saving && !this.conflict) this.value = value; };
  cancel = (): void => { if (!this.saving) this.editing = false; };
  reload = async (): Promise<void> => { if (!this.saving && !this.disposed) await this.reloadNode(); };

  save = async (): Promise<void> => {
    const node = this.current;
    if (this.disposed || !node || !this.canSave) return;
    const generation = this.generation;
    this.pendingIds.add(node.id);
    this.saving = true;
    this.message = '';
    this.notice = '';
    try {
      const updated = nodeSummarySchema.parse(await this.api.updateDescription(node.id, node.revision, { description: this.value }));
      if (this.disposed || generation !== this.generation) return;
      if (updated.id !== node.id || updated.kind !== node.kind || updated.revision <= node.revision) throw new Error('Unexpected description result');
      this.accept(updated);
      this.current = updated;
      this.editing = false;
      this.notice = 'Description saved.';
    } catch (error) {
      if (this.disposed || generation !== this.generation) return;
      if (error instanceof HttpError && error.status === 412) {
        this.conflict = true;
        this.message = 'This item changed. Reload before editing its description again.';
      } else if (error instanceof AuthenticationRequiredError || error instanceof HttpError && [403, 404].includes(error.status)) {
        this.availability = error instanceof AuthenticationRequiredError ? 'sign-in' : 'denied';
        this.editing = false;
        this.message = 'Description editing is no longer available.';
      } else {
        this.conflict = true;
        this.message = 'The description could not be confirmed. Reload before trying again.';
      }
    } finally {
      this.pendingIds.delete(node.id);
      if (!this.disposed && generation === this.generation) this.saving = false;
    }
  };

  dispose = (): void => { this.reset(); this.disposed = true; };
}
