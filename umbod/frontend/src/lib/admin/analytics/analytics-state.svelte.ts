import { z } from 'zod';
import { AuthenticationRequiredError, HttpError } from '../infrastructure/transport';
import type { LogCountSource } from './port';
import type { LogCountQuery, LogCountResponse } from './domain/schemas';
import { QueryDraft, dimensionLabels } from './query-draft.svelte';
import { ActivityCoverage } from './activity-coverage.svelte';
import { FilterChoices } from './filter-choices.svelte';
import { reportOptions, reports, reportValue, resolveReport, type ReportId } from './reports';

type ReadonlyValue<T> = T extends object ? { readonly [Key in keyof T]: ReadonlyValue<T[Key]> } : T;

interface Submission {
  report: ReportId;
  query: LogCountQuery;
  fingerprint: string;
}

interface SubmittedResult extends Submission {
  response: LogCountResponse;
}

const detailSchema = z.object({ detail: z.string() });

export class AnalyticsState {
  readonly draft = new QueryDraft();
  readonly reportRange = new QueryDraft();
  private reportValue = $state<ReportId>('tools');
  readonly choices: FilterChoices;
  readonly coverage: ActivityCoverage;
  private resultValue = $state.raw<SubmittedResult | undefined>();
  private pendingValue = $state(false);
  private errorValue = $state('');
  private validationValue = $state('');
  private accessLostValue = $state(false);
  private failedSubmission: Submission | undefined;
  private generation = 0;
  private disposed = false;
  private controller: AbortController | undefined;

  constructor(private readonly source: LogCountSource, private readonly now: () => Date = () => new Date()) {
    this.coverage = new ActivityCoverage(source, this.loseAccess);
    this.choices = new FilterChoices(this.draft, source, now, this.loseAccess);
  }

  get report(): ReportId { return this.reportValue; }
  get custom(): boolean { return this.report === 'custom'; }
  get formDraft(): QueryDraft { return this.custom ? this.draft : this.reportRange; }
  get fingerprint(): string { return this.formDraft.fingerprint; }
  get narrowedSession(): string | undefined {
    return this.submittedReport ? this.resultValue?.query.filters.find((filter) => filter.dimension === 'session_id')?.values[0] : undefined;
  }
  isSessionGroup(group: ReadonlyValue<LogCountResponse['rows'][number]['groups'][number]>): boolean {
    return this.submittedReport !== undefined && group.dimension === 'session_id' && group.value.kind === 'present' && group.value.value !== '';
  }
  get submittedCustom(): boolean { return this.resultValue?.report === 'custom'; }
  private get submittedReport(): typeof reports[keyof typeof reports] | undefined {
    const report = this.resultValue?.report;
    return report && report !== 'custom' ? reports[report] : undefined;
  }
  get submittedFilters(): ReadonlyArray<ReadonlyValue<LogCountQuery['filters'][number]>> {
    const filters = this.resultValue?.query.filters ?? [];
    return this.submittedCustom ? filters : filters.filter((filter) => filter.dimension !== 'activity_kind');
  }
  get resultLabel(): string { return this.submittedReport?.label ?? 'Results'; }
  get countLabel(): string { return this.submittedReport?.countLabel ?? 'Log count'; }
  get explanation(): string { return this.submittedReport?.explanation ?? ''; }
  formatValue(dimension: LogCountQuery['group_by'][number], value: string): string { return this.submittedCustom ? value : reportValue(dimension, value); }
  setReport(value: string): void {
    if (reportOptions.some((option) => option.value === value)) {
      this.reportValue = value as ReportId;
      if (!this.custom) this.choices.close();
    }
  }

  get result(): ReadonlyValue<SubmittedResult> | undefined { return this.resultValue; }
  get tableRows(): ReadonlyArray<ReadonlyValue<LogCountResponse['rows'][number]>> {
    return this.resultValue?.response.rows ?? [];
  }
  get pending(): boolean { return this.pendingValue; }
  get page(): number { return Math.floor((this.resultValue?.query.pagination.offset ?? 0) / 100) + 1; }
  get canGoPrevious(): boolean { return !this.pending && (this.resultValue?.query.pagination.offset ?? 0) > 0; }
  get canGoNext(): boolean { return !this.pending && Boolean(this.resultValue?.response.has_more); }
  get error(): string { return this.errorValue; }
  get validation(): string { return this.validationValue; }
  get accessLost(): boolean { return this.accessLostValue; }
  get changed(): boolean { return this.resultValue !== undefined && (this.report !== this.resultValue.report || this.fingerprint !== this.resultValue.fingerprint); }
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

  async run(): Promise<void> {
    if (this.disposed || this.accessLost) return;
    this.validationValue = '';
    let query: LogCountQuery;
    try {
      query = this.report === 'custom' ? this.draft.resolve(this.now()) : resolveReport(this.report, this.reportRange.resolveTimeRange(this.now()));
    } catch (failure) {
      this.validationValue = failure instanceof Error ? failure.message : 'Check your query settings.';
      return;
    }
    await this.submit({ query, fingerprint: this.fingerprint, report: this.report });
  }

  async previous(): Promise<void> {
    if (this.canGoPrevious) await this.navigate(-100);
  }

  async next(): Promise<void> {
    if (this.canGoNext) await this.navigate(100);
  }

  async retry(): Promise<void> {
    if (!this.pending && this.failedSubmission) await this.submit(this.failedSubmission);
  }

  async narrowToSession(session: string): Promise<void> {
    if (session !== '') await this.changeSessionScope(session);
  }

  async allSessions(): Promise<void> {
    if (this.narrowedSession !== undefined) await this.changeSessionScope(undefined);
  }

  async inspectClassifications(): Promise<void> {
    const result = this.resultValue;
    if (!result || !this.submittedReport || this.pending || this.accessLost || this.disposed) return;
    this.setReport('logs');
    await this.submit({
      report: 'logs',
      fingerprint: result.fingerprint,
      query: {
        ...resolveReport('logs', result.query.time_range),
        filters: result.query.filters.filter((filter) => filter.dimension !== 'activity_kind')
      }
    });
  }

  private async changeSessionScope(session: string | undefined): Promise<void> {
    const result = this.resultValue;
    if (!result || !this.submittedReport || this.pending) return;
    await this.submit({
      query: {
        ...result.query,
        filters: [
          ...result.query.filters.filter((filter) => filter.dimension !== 'session_id'),
          ...(session === undefined ? [] : [{ dimension: 'session_id' as const, values: [session] }])
        ],
        pagination: { limit: 100, offset: 0 }
      },
      report: result.report,
      fingerprint: result.fingerprint
    });
  }

  private async navigate(change: number): Promise<void> {
    const result = this.resultValue;
    if (!result) return;
    await this.submit({
      query: { ...result.query, pagination: { limit: 100, offset: result.query.pagination.offset + change } },
      report: result.report,
      fingerprint: result.fingerprint
    });
  }

  private async submit({ query, fingerprint, report }: Submission): Promise<void> {
    if (this.disposed || this.accessLost) return;
    this.failedSubmission = undefined;
    this.validationValue = '';
    const generation = ++this.generation;
    this.controller?.abort();
    this.controller = new AbortController();
    this.pendingValue = true;
    this.errorValue = '';
    try {
      const response = await this.source.query(query, this.controller.signal);
      if (this.disposed || generation !== this.generation) return;
      this.resultValue = { query, response, fingerprint, report };
      if (report === 'custom') this.coverage.clear();
      else void this.coverage.load(query);
    } catch (failure) {
      if (this.disposed || generation !== this.generation) return;
      this.failedSubmission = { query, fingerprint, report };
      if (failure instanceof AuthenticationRequiredError || (failure instanceof HttpError && [401, 403].includes(failure.status))) {
        this.loseAccess();
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

  private loseAccess = (): void => {
    this.generation++;
    this.controller?.abort();
    this.pendingValue = false;
    this.resultValue = undefined;
    this.failedSubmission = undefined;
    this.accessLostValue = true;
    this.errorValue = 'Administration access is no longer available. Sign in again or contact your administrator.';
    this.choices.dispose();
    this.coverage.dispose();
  };

  dispose(): void {
    this.coverage.dispose();
    this.choices.dispose();
    this.disposed = true;
    this.failedSubmission = undefined;
    this.generation++;
    this.controller?.abort();
    this.pendingValue = false;
    this.resultValue = undefined;
  }
}
