import { z } from 'zod';
import { AuthenticationRequiredError, HttpError } from '../infrastructure/transport';
import type { LogCountSource } from './port';
import type { LogCountQuery, LogCountResponse } from './domain/schemas';
import { QueryDraft, dimensionLabels } from './query-draft.svelte';

type ReadonlyValue<T> = T extends object ? { readonly [Key in keyof T]: ReadonlyValue<T[Key]> } : T;

interface SubmittedResult {
  query: LogCountQuery;
  response: LogCountResponse;
  fingerprint: string;
}

const detailSchema = z.object({ detail: z.string() });

export class AnalyticsState {
  readonly draft = new QueryDraft();
  private resultValue = $state.raw<SubmittedResult | undefined>();
  private pendingValue = $state(false);
  private errorValue = $state('');
  private validationValue = $state('');
  private accessLostValue = $state(false);
  private generation = 0;
  private disposed = false;
  private controller: AbortController | undefined;

  constructor(private readonly source: LogCountSource, private readonly now: () => Date = () => new Date()) {}

  get result(): ReadonlyValue<SubmittedResult> | undefined { return this.resultValue; }
  get tableRows(): ReadonlyArray<ReadonlyValue<LogCountResponse['rows'][number]>> {
    return this.resultValue?.response.rows ?? [];
  }
  get pending(): boolean { return this.pendingValue; }
  get error(): string { return this.errorValue; }
  get validation(): string { return this.validationValue; }
  get accessLost(): boolean { return this.accessLostValue; }
  get changed(): boolean { return this.resultValue !== undefined && this.draft.fingerprint !== this.resultValue.fingerprint; }
  get total(): number { return this.resultValue?.response.rows.reduce((total, row) => total + row.count, 0) ?? 0; }
  get groupCount(): number {
    if (this.total === 0) return 0;
    return new Set(this.resultValue?.response.rows.map((row) => JSON.stringify([...row.groups].sort((left, right) => left.dimension.localeCompare(right.dimension)))) ?? []).size;
  }
  get groupingLabel(): string {
    return this.resultValue?.query.group_by.map((dimension) => dimensionLabels[dimension]).join(' → ') || 'All logs';
  }
  get bucketLabel(): string {
    const bucket = this.resultValue?.query.bucketing;
    return bucket?.kind === 'fixed' ? `${bucket.width} buckets` : 'No time buckets';
  }
  get hasUnaddedValues(): boolean { return Object.values(this.draft.inputs).some((value) => value !== ''); }

  async run(): Promise<void> {
    if (this.disposed || this.accessLost) return;
    this.validationValue = '';
    let query: LogCountQuery;
    try {
      if (this.hasUnaddedValues) throw new Error('Add or clear the typed filter values before running the query.');
      query = this.draft.resolve(this.now());
    } catch (failure) {
      this.validationValue = failure instanceof Error ? failure.message : 'Check your query settings.';
      return;
    }
    const fingerprint = this.draft.fingerprint;
    const generation = ++this.generation;
    this.controller?.abort();
    this.controller = new AbortController();
    this.pendingValue = true;
    this.errorValue = '';
    try {
      const response = await this.source.query(query, this.controller.signal);
      if (this.disposed || generation !== this.generation) return;
      this.resultValue = { query, response, fingerprint };
    } catch (failure) {
      if (this.disposed || generation !== this.generation) return;
      if (failure instanceof AuthenticationRequiredError || (failure instanceof HttpError && [401, 403].includes(failure.status))) {
        this.resultValue = undefined;
        this.accessLostValue = true;
        this.errorValue = 'Administration access is no longer available. Sign in again or contact your administrator.';
      } else if (failure instanceof HttpError && failure.status === 503) {
        this.errorValue = 'Log analytics is disabled or temporarily unavailable. Ask your administrator to enable analytics, or try again later.';
      } else if (failure instanceof HttpError && failure.status === 422) {
        const detail = detailSchema.safeParse(failure.body);
        this.errorValue = detail.success ? detail.data.detail : 'The query could not be completed. Narrow the time range or filters, or remove grouping dimensions.';
      } else {
        this.errorValue = 'The log-count query failed. Check your connection and try again.';
      }
    } finally {
      if (!this.disposed && generation === this.generation) this.pendingValue = false;
    }
  }

  dispose(): void {
    this.disposed = true;
    this.generation++;
    this.controller?.abort();
    this.pendingValue = false;
    this.resultValue = undefined;
  }
}
