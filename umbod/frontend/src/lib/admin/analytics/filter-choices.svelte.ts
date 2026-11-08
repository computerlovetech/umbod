import { AuthenticationRequiredError, HttpError } from '../infrastructure/transport';
import { dimensionSchema, type Dimension, type LogCountQuery } from './domain/schemas';
import type { LogCountSource } from './port';
import type { QueryDraft } from './query-draft.svelte';

interface Choice {
  readonly value: string;
  readonly label: string;
}

export class FilterChoices {
  private openValue = $state(false);
  private dimensionValue = $state<Dimension>('source');
  private searchValue = $state('');
  private pendingValue = $state('');
  private errorValue = $state('');
  private entries = $state.raw<readonly Choice[]>([]);
  private signature = $state<string | undefined>();
  private controller: AbortController | undefined;
  private generation = 0;
  private disposed = false;

  constructor(
    private readonly draft: QueryDraft,
    private readonly source: LogCountSource,
    private readonly now: () => Date,
    private readonly onAccessLost: () => void
  ) {}

  get open(): boolean { return this.openValue; }
  get dimension(): Dimension { return this.dimensionValue; }
  get search(): string { return this.searchValue; }
  get pending(): string { return this.pendingValue; }
  get error(): string { return this.errorValue; }
  get stale(): boolean { return this.signature !== undefined && this.signature !== this.timeSignature; }
  get options(): Choice[] {
    if (this.stale || this.pending || this.error || !this.open) return [];
    const selected = this.draft.filters[this.dimension];
    return this.entries.filter((entry) => !selected.includes(JSON.parse(entry.value) as string)
      && ((JSON.parse(entry.value) as string) || 'Empty value').toLowerCase().includes(this.search.toLowerCase())).map((entry) => ({ ...entry }));
  }
  get emptyMessage(): string {
    if (this.stale) return 'The time range changed. Refresh to load existing values.';
    if (this.pending || this.error || !this.open || this.options.length > 0) return '';
    return this.search ? 'No matching values.' : 'No unselected values in this time range.';
  }
  private get timeSignature(): string {
    return JSON.stringify([this.draft.preset, this.draft.start, this.draft.end, this.draft.offset]);
  }

  show = async (): Promise<void> => {
    if (this.disposed) return;
    this.openValue = true;
    await this.refresh();
  };

  close = (): void => {
    this.openValue = false;
    this.cancel();
    this.entries = [];
    this.signature = undefined;
    this.errorValue = '';
  };

  setDimension = async (value: string): Promise<void> => {
    const parsed = dimensionSchema.safeParse(value);
    if (this.disposed || !parsed.success || parsed.data === this.dimension) return;
    this.cancel();
    this.dimensionValue = parsed.data;
    this.searchValue = '';
    this.entries = [];
    this.signature = undefined;
    await this.refresh();
  };

  setSearch = (value: string): void => { this.searchValue = value; };

  refresh = async (): Promise<void> => {
    if (this.disposed || !this.open) return;
    this.cancel();
    const generation = this.generation;
    const dimension = this.dimension;
    this.signature = this.timeSignature;
    this.entries = [];
    this.errorValue = '';
    let time_range: LogCountQuery['time_range'];
    try {
      time_range = this.draft.resolveTimeRange(this.now());
    } catch {
      this.errorValue = 'Choose a valid time range before loading values.';
      return;
    }
    this.pendingValue = 'Loading existing values…';
    this.controller = new AbortController();
    try {
      const entries: Choice[] = [];
      let offset = 0;
      while (true) {
        const response = await this.source.query({ time_range, group_by: [dimension], bucketing: { kind: 'none' }, pagination: { limit: 1000, offset }, filters: [] }, this.controller.signal);
        if (this.disposed || generation !== this.generation) return;
        entries.push(...response.rows.flatMap((row): Choice[] => {
          const attribute = row.groups.find((group) => group.dimension === dimension)?.value;
          return attribute?.kind === 'present'
            ? [{ value: JSON.stringify(attribute.value), label: `${attribute.value === '' ? 'Empty value' : attribute.value} (${row.count})` }]
            : [];
        }));
        if (!response.has_more) break;
        offset += 1000;
      }
      this.entries = [...new Map<string, Choice>(entries.map((entry) => [entry.value, entry])).values()];
    } catch (failure) {
      if (this.disposed || generation !== this.generation) return;
      if (failure instanceof AuthenticationRequiredError || (failure instanceof HttpError && [401, 403].includes(failure.status))) {
        this.onAccessLost();
      } else {
        this.errorValue = failure instanceof HttpError && failure.status === 422
          ? 'Existing values could not be loaded. Check the time range and query settings, then refresh.'
          : 'Existing values could not be loaded. Check your settings or connection and try again.';
      }
    } finally {
      if (generation === this.generation) this.pendingValue = '';
    }
  };

  choose = (encodedValue: string): void => {
    if (this.disposed || !this.options.some((entry) => entry.value === encodedValue)) return;
    this.draft.selectFilter(this.dimension, JSON.parse(encodedValue) as string);
    this.searchValue = '';
  };

  dispose = (): void => {
    this.close();
    this.disposed = true;
  };

  private cancel(): void {
    this.generation++;
    this.controller?.abort();
    this.pendingValue = '';
  }
}
