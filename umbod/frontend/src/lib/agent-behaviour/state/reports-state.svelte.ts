import { AuthenticationRequiredError, HttpError } from '#lib/admin/infrastructure/transport.js';
import type { ReportReadsPort } from '../api';
import { querySchema, type ReportQuery, type ReportPage, type DiagnosticReport } from '../domain/schemas';

export interface ReportLabel {
  readonly id: string;
  readonly name: string;
}

export interface ReportLabels {
  readonly patterns: readonly ReportLabel[];
  readonly playbooks: readonly ReportLabel[];
  readonly seenPage?: (page: ReportPage) => void;
  readonly seenDetail?: (detail: DiagnosticReport) => void;
  readonly clear?: () => void;
}

export class ReportsState {
  private queryValue = $state<ReportQuery>({ limit: 25, offset: 0 });
  private draftQueryValue = $state<ReportQuery>({ limit: 25, offset: 0 });
  private summaryValue = $state('All reporting settings · All patterns · All statuses');
  private pageValue = $state<ReportPage | null>(null);
  private detailValue = $state<DiagnosticReport | null>(null);
  private busyValue = $state(false);
  private detailBusyValue = $state(false);
  private messageValue = $state('');
  protected disposed = false;
  private listRequest: AbortController | null = null;
  private detailRequest: AbortController | null = null;
  constructor(private readonly api: ReportReadsPort, private readonly revoke: () => void, private readonly labels: () => ReportLabels = () => ({ patterns: [], playbooks: [] })) {}
  get query(): Readonly<ReportQuery> { return { ...this.queryValue }; }
  get draftQuery(): Readonly<ReportQuery> { return { ...this.draftQueryValue }; }
  get querySummary(): string { return this.summaryValue; }
  get page(): { readonly items: readonly Readonly<ReportPage['items'][number]>[]; readonly total: number } { return this.pageValue ? structuredClone($state.snapshot(this.pageValue)) : { items: [], total: 0 }; }
  get detail(): DiagnosticReport | null { return this.detailValue ? structuredClone($state.snapshot(this.detailValue)) : null; }
  get busy(): boolean { return this.busyValue; }
  get hasResult(): boolean { return this.pageValue !== null; }
  get detailBusy(): boolean { return this.detailBusyValue; }
  get message(): string { return this.messageValue; }
  get patterns(): readonly ReportLabel[] { return this.labels().patterns; }
  get reportingOptions(): readonly ReportLabel[] { return this.labels().playbooks; }
  reportingName = (id: string): string => this.reportingOptions.find((setting): boolean => setting.id === id)?.name ?? 'Previous reporting settings';
  patternName = (id: string): string => this.patterns.find((pattern): boolean => pattern.id === id)?.name ?? 'Removed pattern';

  get hasNext(): boolean { return this.queryValue.offset + this.queryValue.limit < (this.pageValue?.total ?? 0); }
  get pageNumber(): number { return Math.floor(this.queryValue.offset / this.queryValue.limit) + 1; }
  get assessments(): Array<DiagnosticReport['submission']['assessments'][number] & { pattern: DiagnosticReport['instructions']['patterns'][number] | undefined }> {
    const detail = this.detail;
    return detail?.submission.assessments.map((assessment) => ({ ...assessment, pattern: detail.instructions.patterns.find((pattern): boolean => pattern.id === assessment.pattern_id) })) ?? [];
  }
  private failure = (error: unknown, fallback: string = 'Entries could not be loaded. Try again.'): void => {
    if (error instanceof AuthenticationRequiredError || (error instanceof HttpError && [401, 403].includes(error.status))) { this.revoke(); return; }
    this.messageValue = error instanceof HttpError && error.status === 404 ? 'This entry is no longer available.' : fallback;
  };
  filter = (key: 'playbook_id' | 'pattern_id' | 'status', value: string): void => {
    if (this.disposed || this.detailBusyValue) return;
    const parsed = querySchema.safeParse({ ...this.draftQueryValue, [key]: value || undefined, offset: 0 });
    if (!parsed.success) { this.messageValue = 'Select a valid entry filter.'; return; }
    this.draftQueryValue = parsed.data;
  };
  paginate = (direction: number): void => { if (this.disposed || this.detailBusyValue) return; this.queryValue = { ...this.queryValue, offset: Math.max(0, this.queryValue.offset + direction * this.queryValue.limit) }; void this.load(); };
  resetQuery = (): void => {
    if (this.disposed) return;
    this.draftQueryValue = { limit: 25, offset: 0 };
  };
  runQuery = async (): Promise<boolean> => {
    if (this.disposed || this.detailBusyValue) return false;
    const parsed = querySchema.safeParse({ ...this.draftQueryValue, offset: 0 });
    if (!parsed.success) { this.messageValue = 'Select a valid entry filter.'; return false; }
    this.queryValue = parsed.data;
    const statuses = { observed: 'Observed', not_observed: 'Not observed', not_assessed: 'Not assessed' };
    this.summaryValue = [this.queryValue.playbook_id ? this.reportingName(this.queryValue.playbook_id) : 'All reporting settings', this.queryValue.pattern_id ? this.patternName(this.queryValue.pattern_id) : 'All patterns', this.queryValue.status ? statuses[this.queryValue.status] : 'All statuses'].join(' · ');
    return this.load();
  };
  start = (): void => {
    if (this.disposed) return;
    this.stop();
    this.resetQuery();
    void this.runQuery();
  };
  stop = (): void => {
    this.listRequest?.abort();
    this.listRequest = null;
    this.close();
    this.pageValue = null;
    this.labels().clear?.();
    this.busyValue = false;
    this.messageValue = '';
  };
  load = async (): Promise<boolean> => {
    if (this.disposed || this.detailBusyValue) return false;
    this.listRequest?.abort(); const request = new AbortController(); this.listRequest = request;
    this.busyValue = true; this.messageValue = ''; this.pageValue = null; this.close();
    try {
      const page = await this.api.list({ ...this.queryValue }, request.signal);
      if (this.disposed || this.listRequest !== request) return false;
      this.labels().seenPage?.(page);
      this.pageValue = page;
      return true;
    }
    catch (error) { if (!this.disposed && this.listRequest === request) this.failure(error); return false; }
    finally { if (!this.disposed && this.listRequest === request) this.busyValue = false; }
  };
  async open(id: string): Promise<void> {
    if (this.disposed) return;
    this.close(); this.messageValue = '';
    await this.runDetailRequest(async (request): Promise<void> => {
      const detail = await this.api.get(id, request.signal);
      if (!this.isCurrentDetailRequest(request)) return;
      this.labels().seenDetail?.(detail);
      this.detailValue = detail;
    });
  }

  protected isCurrentDetailRequest(request: AbortController): boolean {
    return !this.disposed && this.detailRequest === request;
  }

  protected async runDetailRequest(operation: (request: AbortController) => Promise<void>, fallback?: string): Promise<void> {
    const request = new AbortController(); this.detailRequest = request; this.detailBusyValue = true;
    try { await operation(request); }
    catch (error) { if (this.isCurrentDetailRequest(request)) this.failure(error, fallback); }
    finally { if (this.isCurrentDetailRequest(request)) this.detailBusyValue = false; }
  }

  protected closeDetail(): void {
    this.detailRequest?.abort(); this.detailRequest = null; this.detailValue = null; this.detailBusyValue = false;
  }

  close = (): void => this.closeDetail();
  dispose = (): void => { this.disposed = true; this.stop(); };
}
