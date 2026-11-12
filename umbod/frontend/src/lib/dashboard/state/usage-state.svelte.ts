import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';
import type { UsagePort } from '../api';
import type { PersonalUsage, UsageDays } from '../domain/usage-schemas';

import { projectUsage } from '../chart-projections';

type UsagePhase = 'idle' | 'loading' | 'ready' | 'error' | 'unavailable' | 'sign-in' | 'forbidden';

export class UsageState {
  private currentDays = $state<UsageDays>(7);
  private currentPhase = $state<UsagePhase>('idle');
  private currentSnapshot = $state.raw<PersonalUsage | undefined>();
  private chartProjection = $derived(projectUsage(this.currentSnapshot));
  private expectedIdentity = '';
  private revision = 0;
  private request: AbortController | undefined;
  private active = true;
  private identitySourceAvailable = true;
  private started = false;

  constructor(private readonly port: UsagePort, private readonly onAuthenticationLost: () => void) {}

  get charts(): ReturnType<typeof projectUsage> { return this.chartProjection; }
  get days(): UsageDays { return this.currentDays; }
  get phase(): UsagePhase { return this.currentPhase; }
  get snapshot(): PersonalUsage | undefined { return this.currentSnapshot; }
  get pending(): boolean { return this.currentPhase === 'loading'; }

  private clear = (): void => {
    this.revision++;
    this.request?.abort();
    this.currentSnapshot = undefined;
  };

  setIdentitySourceAvailable = (available: boolean): void => {
    this.identitySourceAvailable = available;
    if (!available) this.authenticationLost();
  };

  reconcileIdentity = (identity: string): void => {
    if (!this.active || (this.expectedIdentity === identity && (!this.currentSnapshot || this.currentSnapshot.identity_key === identity))) return;
    const changed = (this.expectedIdentity !== '' && this.expectedIdentity !== identity)
      || (this.currentSnapshot !== undefined && this.currentSnapshot.identity_key !== identity);
    this.expectedIdentity = identity;
    if (changed) {
      this.clear();
      this.currentPhase = 'idle';
      if (this.started) void this.refresh();
    }
  };

  selectPeriod = (value: string): void => {
    if (!this.active || (value !== '7' && value !== '30') || Number(value) === this.currentDays) return;
    this.currentDays = value === '7' ? 7 : 30;
    void this.refresh();
  };

  revalidate = (): Promise<void> => {
    this.expectedIdentity = '';
    return this.refresh();
  };

  authenticationLost = (phase: 'sign-in' | 'forbidden' = 'sign-in'): void => {
    this.clear();
    this.expectedIdentity = '';
    this.currentPhase = phase;
  };

  refresh = async (): Promise<void> => {
    if (!this.active || !this.identitySourceAvailable) return;
    this.started = true;
    this.clear();
    const revision = this.revision;
    const days = this.currentDays;
    const request = new AbortController();
    this.request = request;
    this.currentPhase = 'loading';
    try {
      const result = await this.port.get(days, request.signal);
      if (!this.active || revision !== this.revision || request.signal.aborted || days !== this.currentDays) return;
      if ((this.expectedIdentity !== '' && result.identity_key !== this.expectedIdentity) || result.daily.length !== days) {
        this.currentPhase = 'error';
        return;
      }
      this.expectedIdentity = result.identity_key;
      this.currentSnapshot = result;
      this.currentPhase = 'ready';
    } catch (error) {
      if (!this.active || revision !== this.revision || request.signal.aborted) return;
      if (error instanceof AuthenticationRequiredError || (error instanceof HttpError && error.status === 401)) {
        this.authenticationLost();
        this.onAuthenticationLost();
      } else if (error instanceof HttpError && error.status === 403) this.authenticationLost('forbidden');
      else this.currentPhase = error instanceof HttpError && error.status === 503 ? 'unavailable' : 'error';
    }
  };

  dispose = (): void => {
    this.active = false;
    this.clear();
    this.expectedIdentity = '';
    this.currentPhase = 'idle';
  };
}
