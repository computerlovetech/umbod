import { AuthenticationRequiredError, HttpError } from '../infrastructure/transport';
import { logCountQuerySchema, logCountResponseSchema, type LogCountQuery } from './domain/schemas';
import type { LogCountSource } from './port';

interface ClassificationCounts {
  readonly recognized: number;
  readonly other: number;
}

export class ActivityCoverage {
  private countsValue = $state.raw<ClassificationCounts | undefined>();
  private pendingValue = $state(false);
  private errorValue = $state('');
  private queryValue: LogCountQuery | undefined;
  private signature = '';
  private generation = 0;
  private controller: AbortController | undefined;
  private disposed = false;

  constructor(private readonly source: LogCountSource, private readonly onAccessLost: () => void) {}

  get counts(): ClassificationCounts | undefined { return this.countsValue; }
  get hasLogs(): boolean { return this.countsValue !== undefined && this.countsValue.recognized + this.countsValue.other > 0; }
  get pending(): boolean { return this.pendingValue; }
  get error(): string { return this.errorValue; }

  load = async (submittedQuery: LogCountQuery): Promise<void> => {
    if (this.disposed) return;
    const query = logCountQuerySchema.parse({
      time_range: submittedQuery.time_range,
      filters: submittedQuery.filters.filter((filter) => filter.dimension !== 'activity_kind'),
      group_by: ['activity_kind'],
      bucketing: { kind: 'none' },
      pagination: { limit: 1000, offset: 0 }
    });
    const signature = JSON.stringify([query.time_range, [...query.filters].sort((left, right) => left.dimension.localeCompare(right.dimension)).map((filter) => ({ ...filter, values: [...filter.values].sort() }))]);
    if (signature === this.signature) return;
    this.clear();
    this.signature = signature;
    this.queryValue = query;
    await this.fetch();
  };

  retry = async (): Promise<void> => {
    if (!this.disposed && !this.pending && this.queryValue) await this.fetch();
  };

  private async fetch(): Promise<void> {
    const query = this.queryValue;
    if (!query) return;
    const generation = ++this.generation;
    this.controller?.abort();
    const controller = new AbortController();
    this.controller = controller;
    this.pendingValue = true;
    this.errorValue = '';
    this.countsValue = undefined;
    try {
      const counts = new Map<string, { recognized: boolean; count: number }>();
      let offset = 0;
      while (true) {
        const response = logCountResponseSchema.parse(await this.source.query({ ...query, pagination: { limit: 1000, offset } }, controller.signal));
        if (this.disposed || generation !== this.generation) return;
        for (const row of response.rows) {
          if (row.bucket.kind !== 'none' || row.groups.length !== 1 || row.groups[0].dimension !== 'activity_kind') throw new Error('Invalid classification grouping');
          const value = row.groups[0].value;
          counts.set(JSON.stringify(value), { recognized: value.kind === 'present' && value.value !== '', count: row.count });
        }
        if (!response.has_more) break;
        offset += 1000;
      }
      this.countsValue = [...counts.values()].reduce((total, entry) => ({
        recognized: total.recognized + (entry.recognized ? entry.count : 0),
        other: total.other + (entry.recognized ? 0 : entry.count)
      }), { recognized: 0, other: 0 });
    } catch (failure) {
      if (this.disposed || generation !== this.generation) return;
      if (failure instanceof AuthenticationRequiredError || (failure instanceof HttpError && [401, 403].includes(failure.status))) {
        this.clear();
        this.onAccessLost();
      } else {
        this.errorValue = 'Log classification counts could not be loaded. Try again.';
      }
    } finally {
      if (generation === this.generation) this.pendingValue = false;
    }
  }

  clear = (): void => {
    this.generation++;
    this.controller?.abort();
    this.pendingValue = false;
    this.countsValue = undefined;
    this.errorValue = '';
    this.queryValue = undefined;
    this.signature = '';
  };

  dispose = (): void => {
    this.clear();
    this.disposed = true;
  };
}
