import { AuthenticationRequiredError, HttpError } from '#lib/admin/infrastructure/transport.js';
import { projectUsage } from '#lib/dashboard/chart-projections.js';
import type { ActivityApi } from './domain/activity-api.js';
import type {
  ActivityDays, ActivityOverview, ActivitySessionKey, ActivitySessionPage, ActivitySessionReport
} from './domain/activity-schemas.js';
import { sessionIdentity } from './presentation.js';

export type ActivitySource = 'harness' | 'mcp';
type Failure = 'error' | 'unavailable' | 'missing';
type ReadResult<T> = { kind: Failure } | { kind: 'ready'; value: T };
type ReadState<T> = ReadResult<T> | { kind: 'idle' | 'loading' };

export class ActivityState {
  days = $state<ActivityDays>(7);
  source = $state<ActivitySource>('mcp');
  access = $state<'allowed' | 'sign-in' | 'forbidden'>('allowed');
  search = $state('');
  overview = $state.raw<ReadState<ActivityOverview>>({ kind: 'idle' });
  sessions = $state.raw<ReadState<ActivitySessionPage>>({ kind: 'idle' });
  report = $state.raw<ReadState<ActivitySessionReport>>({ kind: 'idle' });
  private selectedKey = $state.raw<ActivitySessionKey>();
  selected = $derived(this.selectedKey ? sessionIdentity(this.selectedKey) : '');
  pagination = $state<'idle' | 'loading' | Failure>('idle');
  overviewSummary = $derived(this.overview.kind === 'ready' ? this.overview.value : undefined);
  sessionPage = $derived(this.sessions.kind === 'ready' ? this.sessions.value : undefined);
  mcpCharts = $derived(projectUsage(this.overviewSummary?.mcp.status === 'available' ? this.overviewSummary.mcp.summary : undefined));
  private overviewRequest?: AbortController;
  private sessionsRequest?: AbortController;
  private detailRequest?: AbortController;
  private disposed = false;

  constructor(
    private readonly api: ActivityApi,
    private readonly identity: string,
    private readonly currentIdentity: () => string
  ) {}

  refresh = async (): Promise<void> => {
    if (!this.hasCurrentIdentity()) return;
    if (this.selectedKey) {
      await this.retrySession();
      return;
    }
    this.access = 'allowed';
    this.resetSessions();
    await Promise.all([this.loadOverview(), this.source === 'harness' ? this.loadSessions() : undefined]);
  };

  selectPeriod = (days: ActivityDays): void => {
    if (days === this.days || this.selectedKey) return;
    this.days = days;
    void this.refresh();
  };

  selectSource = (source: string): void => {
    if (source !== 'harness' && source !== 'mcp') return;
    this.source = source;
    if (source === 'mcp') this.backToOverview();
    else if (this.sessions.kind === 'idle') void this.loadSessions();
  };

  searchSessions = (query: string): void => {
    this.search = query;
    this.resetSessions();
    void this.loadSessions();
  };

  loadSessions = async (): Promise<void> => {
    if (!this.hasCurrentIdentity() || this.access !== 'allowed') return;
    this.sessions = { kind: 'loading' };
    await this.requestSessions();
  };

  loadMore = async (): Promise<void> => {
    if (this.pagination === 'loading' || this.sessions.kind !== 'ready' || this.sessions.value.page.kind !== 'more') return;
    const previous = this.sessions.value;
    this.pagination = 'loading';
    await this.requestSessions(previous);
  };

  openSession = async (key: ActivitySessionKey): Promise<void> => {
    if (!this.hasCurrentIdentity() || this.access !== 'allowed' || this.source !== 'harness') return;
    this.detailRequest?.abort();
    const request = new AbortController();
    this.detailRequest = request;
    this.selectedKey = key;
    this.report = { kind: 'loading' };
    const result = await this.read(request, () => this.api.session(key, request.signal));
    if (result && this.isCurrent(request)) this.report = result;
  };

  retrySession = async (): Promise<void> => {
    if (this.selectedKey) await this.openSession(this.selectedKey);
  };

  backToOverview = (): void => {
    this.detailRequest?.abort();
    this.detailRequest = undefined;
    this.report = { kind: 'idle' };
    this.selectedKey = undefined;
  };

  suspend = (): void => {
    this.overviewRequest?.abort();
    this.overview = { kind: 'idle' };
    this.search = '';
    this.resetSessions();
    this.backToOverview();
  };

  dispose = (): void => {
    this.disposed = true;
    this.suspend();
  };

  private resetSessions(): void {
    this.sessionsRequest?.abort();
    this.sessions = { kind: 'idle' };
    this.pagination = 'idle';
  }

  private async loadOverview(): Promise<void> {
    this.overviewRequest?.abort();
    const request = new AbortController();
    this.overviewRequest = request;
    this.overview = { kind: 'loading' };
    const result = await this.read(request, () => this.api.overview(this.days, request.signal));
    if (!result || !this.isCurrent(request)) return;
    this.overview = result.kind === 'ready' ? result : { kind: 'error' };
  }

  private async requestSessions(previous?: ActivitySessionPage): Promise<void> {
    this.sessionsRequest?.abort();
    const request = new AbortController();
    this.sessionsRequest = request;
    const cursor = previous?.page.kind === 'more' ? previous.page.cursor : undefined;
    const q = this.search;
    const result = await this.read(request, () => this.api.sessions({ days: this.days, q, cursor }, request.signal));
    if (!result || !this.isCurrent(request)) return;
    if (!previous) {
      this.sessions = result;
      return;
    }
    if (result.kind !== 'ready') {
      this.pagination = result.kind;
      return;
    }
    const seen = new Set(previous.sessions.map((session): string => sessionIdentity(session.key)));
    const next = result.value.sessions.filter((session): boolean => !seen.has(sessionIdentity(session.key)));
    this.sessions = { kind: 'ready', value: { ...result.value, sessions: [...previous.sessions, ...next] } };
    this.pagination = 'idle';
  }

  private isCurrent(request: AbortController): boolean {
    return !request.signal.aborted && this.hasCurrentIdentity();
  }

  private hasCurrentIdentity(): boolean {
    return !this.disposed && this.identity !== '' && this.currentIdentity() === this.identity;
  }

  private async read<T extends { identity_key: string }>(request: AbortController, fetch: () => Promise<T>): Promise<ReadResult<T> | undefined> {
    if (!this.isCurrent(request)) return;
    try {
      const value = await fetch();
      return value.identity_key === this.identity ? { kind: 'ready', value } : { kind: 'error' };
    } catch (error) {
      if (!this.isCurrent(request)) return;
      if (error instanceof AuthenticationRequiredError || (error instanceof HttpError && error.status === 401)) {
        this.access = 'sign-in';
        this.suspend();
        return;
      }
      if (error instanceof HttpError && error.status === 403) {
        this.access = 'forbidden';
        this.suspend();
        return;
      }
      if (error instanceof HttpError && error.status === 503) return { kind: 'unavailable' };
      if (error instanceof HttpError && error.status === 404) return { kind: 'missing' };
      return { kind: 'error' };
    }
  }
}
