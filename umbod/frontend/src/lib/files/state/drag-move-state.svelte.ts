import { tick } from 'svelte';
import type { NodeSummary } from '../domain/schemas';
import type { NodeUpdateState } from './node-update-state.svelte';

export const fileMoveTransferType = 'application/x-umbod-file-move';

export class DragMoveState {
  private sourceId = $state('');
  private hoveredId = $state('');
  private pointerX = $state(0);
  private pointerY = $state(0);
  private dragImage: HTMLImageElement | undefined;
  private notice = $state('');
  private message = $state('');
  private operation = $state<symbol | undefined>(undefined);
  private recovery = $state.raw<NodeUpdateState | undefined>(undefined);
  private readonly rows = new Map<string, HTMLElement>();
  private generation = 0;
  private disposed = false;

  constructor(
    private readonly nodes: () => readonly NodeSummary[],
    private readonly updateFor: (id: string) => NodeUpdateState | undefined,
    private readonly blocked: (id: string) => boolean
  ) {}

  get status(): string {
    const source = this.nodes().find((node) => node.id === this.sourceId);
    return source ? `Drop “${source.name}” onto a folder to move it.` : this.notice;
  }
  get dragging(): boolean { return this.sourceId !== ''; }
  get previewName(): string { return this.nodes().find((node) => node.id === this.sourceId)?.name ?? ''; }
  get previewX(): number { return this.pointerX; }
  get previewY(): number { return this.pointerY; }
  get error(): string { return this.message; }
  get pending(): boolean { return this.operation !== undefined; }
  get needsReload(): boolean { return this.recovery?.needsReload === true; }

  canDrag = (id: string): boolean => {
    const node = this.nodes().find((item) => item.id === id);
    const update = this.updateFor(id);
    return !this.disposed && !this.pending && node?.kind === 'file' && update?.canMove === true && !update.pending && !update.open && !update.needsReload && !this.blocked(id);
  };

  attachDragImage = (element: HTMLImageElement): (() => void) => {
    this.dragImage = element;
    return (): void => { if (this.dragImage === element) this.dragImage = undefined; };
  };

  followPointer = (event: DragEvent): void => {
    if (!this.dragging || !Number.isFinite(event.clientX) || !Number.isFinite(event.clientY) || event.clientX === 0 && event.clientY === 0) return;
    const viewport = this.dragImage?.ownerDocument.defaultView;
    this.pointerX = Math.max(8, Math.min(event.clientX + 16, (viewport?.innerWidth ?? event.clientX + 312) - 296));
    this.pointerY = Math.max(8, Math.min(event.clientY + 16, (viewport?.innerHeight ?? event.clientY + 88) - 72));
  };

  attachRow = (id: string): ((row: HTMLElement) => () => void) => (row) => {
    this.rows.set(id, row);
    return (): void => { if (this.rows.get(id) === row) this.rows.delete(id); };
  };

  isSource = (id: string): boolean => this.sourceId === id;
  isTarget = (id: string): boolean => this.hoveredId === id;

  start = (id: string, event: DragEvent): void => {
    const target = event.target;
    if (!event.dataTransfer || !this.canDrag(id) || target instanceof Element && target.closest('button, [role="menu"], dialog')) {
      event.preventDefault();
      return;
    }
    this.cancel();
    this.sourceId = id;
    this.message = '';
    this.notice = '';
    event.dataTransfer.clearData();
    event.dataTransfer.setData(fileMoveTransferType, id);
    event.dataTransfer.effectAllowed = 'move';
    this.followPointer(event);
    if (this.dragImage) event.dataTransfer.setDragImage(this.dragImage, 0, 0);
  };

  over = (id: string, event: DragEvent): void => {
    if (!this.isInternal(event)) return;
    event.preventDefault();
    const allowed = this.destination(id) !== undefined;
    this.hoveredId = allowed ? id : '';
    if (event.dataTransfer) event.dataTransfer.dropEffect = allowed ? 'move' : 'none';
  };

  leave = (id: string, event: DragEvent): void => {
    if (this.hoveredId !== id) return;
    if (event.currentTarget instanceof Element && event.relatedTarget instanceof Node && event.currentTarget.contains(event.relatedTarget)) return;
    this.hoveredId = '';
  };

  drop = (id: string, event: DragEvent): void => {
    if (!this.isInternal(event)) return;
    event.preventDefault();
    const source = this.nodes().find((node) => node.id === this.sourceId);
    const destination = this.destination(id);
    const update = this.updateFor(this.sourceId);
    const matches = event.dataTransfer?.getData(fileMoveTransferType) === this.sourceId;
    this.cancel();
    if (!source || !destination || !update || !matches) return;
    void this.move(source, destination, update);
  };

  preventOutside = (event: DragEvent): void => {
    if (!this.isInternal(event) || event.defaultPrevented) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'none';
    if (event.type === 'drop') this.cancel();
  };

  cancel = (): void => {
    this.sourceId = '';
    this.hoveredId = '';
  };

  reload = async (): Promise<void> => {
    if (!this.pending && this.recovery) await this.recovery.reload();
  };

  reset = (): void => {
    ++this.generation;
    this.cancel();
    this.operation = undefined;
    this.recovery = undefined;
    this.notice = '';
    this.message = '';
  };

  dispose = (): void => { this.reset(); this.rows.clear(); this.disposed = true; };

  private isInternal(event: DragEvent): boolean {
    const types = Array.from(event.dataTransfer?.types ?? []);
    return !this.disposed && !!this.sourceId && types.includes(fileMoveTransferType) && !types.includes('Files');
  }

  private destination(id: string): NodeSummary | undefined {
    if (!this.canDrag(this.sourceId)) return undefined;
    const source = this.nodes().find((node) => node.id === this.sourceId);
    const destination = this.nodes().find((node) => node.id === id);
    const update = this.updateFor(id);
    return destination?.kind === 'directory' && destination.id !== source?.parent_id && update?.canRename === true && !update.pending && !update.open && !this.blocked(id) ? destination : undefined;
  }

  private move = async (source: NodeSummary, destination: NodeSummary, update: NodeUpdateState): Promise<void> => {
    const generation = this.generation;
    const sourceRow = this.rows.get(source.id);
    const restoreFocus = sourceRow?.contains(sourceRow.ownerDocument.activeElement) === true;
    const operation = Symbol();
    this.operation = operation;
    this.recovery = update;
    this.notice = `Moving “${source.name}” to “${destination.name}”…`;
    this.message = '';
    const moved = await update.moveTo(destination);
    if (this.disposed || generation !== this.generation || this.operation !== operation) return;
    this.operation = undefined;
    this.notice = moved ? `Moved “${source.name}” to “${destination.name}”.` : '';
    this.message = moved ? '' : update.error || 'This file can no longer be moved.';
    if (!moved || !restoreFocus || !sourceRow) return;
    await tick();
    const document = sourceRow.ownerDocument;
    if (this.disposed || generation !== this.generation || this.pending || document.activeElement !== document.body) return;
    const focusTarget = this.rows.get(destination.id)?.querySelector<HTMLElement>('a') ?? document.getElementById('files-heading');
    focusTarget?.focus();
  };
}
