import { SvelteSet } from 'svelte/reactivity';
import { HttpError } from '$lib/admin/infrastructure/transport';
import type { FilesystemApi } from '../api';
import { fileNameSchema, nodeSummarySchema, type NodeSummary, type UpdateNode } from '../domain/schemas';
import { MoveDestinationState } from './move-destination-state.svelte';

type Availability = 'hidden' | 'loading' | 'allowed' | 'denied' | 'error';

export class NodeUpdateState {
  private current = $state.raw<NodeSummary | undefined>(undefined);
  private renameAvailability = $state<Availability>('hidden');
  private moveAvailability = $state<Availability>('hidden');
  private mode = $state<'rename' | 'move' | undefined>(undefined);
  private name = $state('');
  private saving = $state(false);
  private message = $state('');
  private stagedDestination = $state.raw<NodeSummary | undefined>(undefined);
  private finishReview: ((outcome: boolean | undefined) => void) | undefined;
  private generation = 0;
  private disposed = false;
  private readonly pendingIds = new SvelteSet<string>();
  private readonly uncertainIds = new SvelteSet<string>();
  readonly destinations: MoveDestinationState;

  constructor(private readonly api: FilesystemApi, private readonly accept: (node: NodeSummary) => void, private readonly reloadNode: () => Promise<void>, personalRoot: () => string | undefined = () => undefined) {
    this.destinations = new MoveDestinationState(api, personalRoot, () => this.pending || this.needsReload);
  }

  get canRename(): boolean { return this.renameAvailability === 'allowed'; }
  get canMove(): boolean { return this.moveAvailability === 'allowed'; }
  get probeFailed(): boolean { return this.renameAvailability === 'error' || this.moveAvailability === 'error'; }
  get open(): boolean { return this.mode !== undefined; }
  get moving(): boolean { return this.mode === 'move'; }
  get draft(): string { return this.name; }
  get title(): string { return this.moving ? `Move “${this.current?.name ?? ''}”` : 'Rename item'; }
  get reviewingDrop(): boolean { return !!this.stagedDestination; }
  get moveWarning(): string { return this.moving ? 'Moving this item may change inherited access. Direct sharing remains unchanged.' : ''; }
  get submitLabel(): string { return this.moving ? this.stagedDestination ? `Move to “${this.stagedDestination.name}”` : this.destinations.selected ? `Move to “${this.destinations.selectedName}”` : 'Move' : 'Rename'; }
  get pending(): boolean { return this.saving || !!this.current && this.pendingIds.has(this.current.id); }
  get error(): string { return this.message || this.destinations.error; }
  get needsReload(): boolean { return !!this.current && this.uncertainIds.has(this.current.id); }
  get canSubmit(): boolean {
    return !!this.current && !this.saving && !this.pendingIds.has(this.current.id) && !this.needsReload && (this.mode === 'rename' ? this.canRename && fileNameSchema.safeParse(this.name).success && this.name !== this.current.name : this.mode === 'move' && this.canMove && (this.reviewingDrop || this.destinations.canSubmit));
  }

  reset = (): void => {
    ++this.generation;
    this.finishReview?.(undefined);
    this.finishReview = undefined;
    this.stagedDestination = undefined;
    this.current = undefined;
    this.mode = undefined;
    this.renameAvailability = 'hidden';
    this.moveAvailability = 'hidden';
    this.message = '';
    this.saving = false;
    this.destinations.reset();
  };

  select = async (node: NodeSummary, eligibility?: { rename: boolean; move: boolean }): Promise<void> => {
    this.reset();
    if (this.disposed) return;
    this.current = node;
    if (typeof node.parent_id !== 'string') return;
    if (eligibility) {
      this.renameAvailability = eligibility.rename ? 'allowed' : 'denied';
      this.moveAvailability = eligibility.move ? 'allowed' : 'denied';
      return;
    }
    await this.checkEligibility();
  };

  acceptUpdatedNode = (node: NodeSummary): void => {
    if (this.current?.id !== node.id || node.revision < this.current.revision) return;
    this.current = node;
    if (!node.permissions.can_discover || !node.permissions.can_write) {
      this.reset();
      this.current = node;
      this.renameAvailability = 'denied';
      this.moveAvailability = 'denied';
    }
  };

  acceptReloadedNode = (node: NodeSummary): void => {
    if (this.disposed) return;
    this.uncertainIds.delete(node.id);
    this.acceptUpdatedNode(node);
  };

  checkEligibility = async (): Promise<void> => {
    const node = this.current;
    if (!node || typeof node.parent_id !== 'string' || this.disposed || this.open) return;
    const generation = ++this.generation;
    this.renameAvailability = 'loading';
    this.moveAvailability = 'loading';
    try {
      await this.api.checkUpdateEligibility(node.id);
      if (this.disposed || generation !== this.generation) return;
      this.renameAvailability = 'allowed';
    } catch (error) {
      if (this.disposed || generation !== this.generation) return;
      this.renameAvailability = this.failure(error);
      this.moveAvailability = this.renameAvailability;
      return;
    }
    try {
      await this.api.checkUpdateEligibility(node.parent_id);
      if (!this.disposed && generation === this.generation) this.moveAvailability = 'allowed';
    } catch (error) {
      if (!this.disposed && generation === this.generation) this.moveAvailability = this.failure(error);
    }
  };

  showRename = (): void => {
    if (this.open || !this.canRename || !this.current || this.pending || this.needsReload) return;
    this.name = this.current.name;
    this.message = '';
    this.mode = 'rename';
  };

  showMove = (): void => {
    if (this.open || !this.canMove || !this.current || typeof this.current.parent_id !== 'string' || this.pending || this.needsReload) return;
    this.mode = 'move';
    this.message = '';
    void this.destinations.open(this.current);
  };

  changeName = (name: string): void => { if (!this.saving && !this.needsReload) this.name = name; };
  cancel = (): void => {
    if (this.saving) return;
    ++this.generation;
    this.finishReview?.(undefined);
    this.finishReview = undefined;
    this.stagedDestination = undefined;
    this.mode = undefined;
    this.destinations.reset();
  };
  reload = async (): Promise<void> => {
    if (this.saving || !this.current) return;
    const id = this.current.id;
    await this.reloadNode();
    if (this.current?.id === id) this.uncertainIds.delete(id);
  };

  submit = async (): Promise<void> => {
    const node = this.current;
    if (!node || !this.canSubmit || this.disposed) return;
    const body = this.mode === 'rename' ? { name: this.name } : { parent_id: (this.stagedDestination ?? this.destinations.selected)!.id };
    const generation = this.generation;
    const finish = this.finishReview;
    this.finishReview = undefined;
    const outcome = await this.persistUpdate(node, body);
    finish?.(outcome);
    if (outcome && generation === this.generation) this.stagedDestination = undefined;
  };

  moveTo = async (destination: NodeSummary): Promise<boolean | undefined> => {
    const node = this.current;
    if (!node || node.kind !== 'file' || destination.kind !== 'directory' || destination.id === node.id || destination.id === node.parent_id || !this.canMove || this.open || this.pending || this.needsReload || this.disposed) return false;
    this.mode = 'move';
    this.message = '';
    const review = new Promise<boolean | undefined>((resolve) => { this.finishReview = resolve; });
    void this.prepareMove(destination, this.generation);
    return review;
  };

  private async prepareMove(destination: NodeSummary, generation: number): Promise<void> {
    try {
      await this.api.checkUpdateEligibility(destination.id);
      if (this.disposed || generation !== this.generation || this.mode !== 'move') return;
      this.stagedDestination = destination;
    } catch (error) {
      if (this.disposed || generation !== this.generation) return;
      this.message = this.failure(error) === 'denied' ? 'You cannot move items to this folder.' : 'Could not check destination. Try again.';
      this.mode = undefined;
      this.finishReview?.(false);
      this.finishReview = undefined;
    }
  }

  private async persistUpdate(node: NodeSummary, body: UpdateNode): Promise<boolean> {
    const generation = this.generation;
    this.pendingIds.add(node.id);
    this.saving = true;
    this.message = '';
    try {
      const updated = nodeSummarySchema.parse(await this.api.updateNode(node.id, node.revision, body));
      if (updated.id !== node.id || updated.kind !== node.kind || updated.revision !== node.revision + 1 || body.parent_id !== undefined && updated.parent_id !== body.parent_id) throw new Error('Unexpected update result');
      if (!this.disposed) this.accept(updated);
      if (this.disposed || generation !== this.generation) return true;
      this.current = updated;
      this.mode = undefined;
      return true;
    } catch (error) {
      const uncertain = !(error instanceof HttpError && [400, 403, 404, 409, 422].includes(error.status));
      if (uncertain) this.uncertainIds.add(node.id);
      if (this.disposed || generation !== this.generation) return false;
      if (error instanceof HttpError && error.status === 409) this.message = 'The name or destination conflicts with another item. Change your selection and try again.';
      else if (error instanceof HttpError && [403, 404].includes(error.status)) {
        this.renameAvailability = 'denied';
        this.moveAvailability = 'denied';
        this.message = 'This action is no longer available.';
      } else this.message = uncertain ? 'The update could not be confirmed. Reload before trying again.' : 'Check the name and destination.';
      return false;
    } finally {
      this.pendingIds.delete(node.id);
      if (!this.disposed && generation === this.generation) this.saving = false;
    }
  }

  private failure(error: unknown): Availability { return error instanceof HttpError && [403, 404].includes(error.status) ? 'denied' : 'error'; }
  dispose = (): void => { this.reset(); this.disposed = true; };
}
