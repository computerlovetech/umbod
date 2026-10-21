import type { AuthorizationPort, ConnectionsPort, PersonalConnectionsApi } from '../api';
import { authorizationHealthSchema, renewalResultSchema, type AuthorizationHealth, type RenewalResult, attemptSchema, emptyRequestSchema, enablementRequestSchema, selectionListSchema, selectionSchema, startAttemptSchema, isTerminalAttempt, type Attempt, type EmptyRequest, type EnablementRequest, type Selection, type SelectionList, type StartAttempt } from '../domain/schemas';

export class InMemoryPersonalConnectionsApi implements PersonalConnectionsApi {
  private readonly selections = new Map<string, Selection>();
  private readonly attempts = new Map<string, StartAttempt>();
  private sequence = 0;
  private readonly health = new Map<string, AuthorizationHealth>();

  constructor(selections: Selection[], health: Readonly<Record<string, AuthorizationHealth>> = {}) {
    for (const [id, value] of Object.entries(health)) this.health.set(id, authorizationHealthSchema.parse(value));
    for (const selection of selectionListSchema.parse({ connectors: selections }).connectors) {
      this.selections.set(selection.connector_id, selection);
    }
  }

  private read = (id: string): Selection => {
    const selection = this.selections.get(id);
    if (!selection) throw new Error('Connection unavailable');
    return selectionSchema.parse(selection);
  };

  private readAttempt = (id: string, attemptId: string): StartAttempt => {
    const attempt = this.attempts.get(id);
    if (!attempt || attempt.attempt_id !== attemptId) throw new Error('Attempt unavailable');
    return startAttemptSchema.parse(attempt);
  };

  readonly connections: ConnectionsPort = {
    list: async (): Promise<SelectionList> => selectionListSchema.parse({ connectors: [...this.selections.values()] }),
    get: async (id: string): Promise<Selection> => this.read(id),
    setEnablement: async (id: string, request: EnablementRequest): Promise<Selection> => {
      const { enabled } = enablementRequestSchema.parse(request);
      const selection = selectionSchema.parse({ ...this.read(id), enabled, runtime_available: false, runtime_unavailable_reason: 'personal_oauth_not_supported' });
      this.selections.set(id, selection);
      if (!enabled) this.invalidateAttempt(id);
      return this.read(id);
    },
    disconnect: async (id: string): Promise<void> => {
      this.selections.set(id, selectionSchema.parse({ ...this.read(id), enabled: false, has_authorization: false, runtime_available: false, runtime_unavailable_reason: 'personal_oauth_not_supported' }));
      this.invalidateAttempt(id);
      this.health.set(id, { state: 'not_authorized' });
    },
    discover: async (id: string, request: EmptyRequest): Promise<void> => {
      emptyRequestSchema.parse(request);
      const selection = this.read(id);
      if (!selection.enabled || !selection.has_authorization || this.health.get(id)?.state !== 'authorized') throw new Error('Discovery unavailable');
    }
  };

  readonly authorization: AuthorizationPort = {
    getHealth: async (id: string): Promise<AuthorizationHealth> => {
      this.read(id);
      return authorizationHealthSchema.parse(this.health.get(id));
    },
    renew: async (id: string, request: EmptyRequest): Promise<RenewalResult> => {
      emptyRequestSchema.parse(request);
      const health = authorizationHealthSchema.parse(this.health.get(id));
      const attempt = this.attempts.get(id);
      if (!this.read(id).enabled || (attempt && !isTerminalAttempt(attempt)) ||
          !['authorized', 'expired'].includes(health.state) || !('refresh_supported' in health) || !health.refresh_supported) {
        throw new Error('Renewal unavailable');
      }
      this.health.set(id, authorizationHealthSchema.parse({
        state: 'authorized', expires_at: new Date(Date.now() + 3600000).toISOString(), refresh_supported: true
      }));
      return renewalResultSchema.parse({ status: 'refreshed', discovery_required: true });
    },
    start: async (id: string, request: EmptyRequest): Promise<StartAttempt> => {
      emptyRequestSchema.parse(request);
      if (!this.read(id).enabled || this.health.get(id)?.state === 'refreshing') throw new Error('Sign-in unavailable');
      const existing = this.attempts.get(id);
      if (existing && !isTerminalAttempt(existing)) throw new Error('Attempt already active');
      const attempt = startAttemptSchema.parse({
        attempt_id: String(++this.sequence), status: 'pending',
        expires_at: new Date(Date.now() + 600000).toISOString(),
        authorization_url: 'https://provider.example/authorize'
      });
      this.attempts.set(id, attempt);
      return startAttemptSchema.parse(attempt);
    },
    get: async (id: string, attemptId: string): Promise<Attempt> => this.view(this.readAttempt(id, attemptId)),
    cancel: async (id: string, attemptId: string): Promise<Attempt> => {
      const attempt = this.readAttempt(id, attemptId);
      if (!isTerminalAttempt(attempt)) this.attempts.set(id, { ...attempt, status: 'cancelled' });
      return this.view(this.readAttempt(id, attemptId));
    }
  };

  private view = (attempt: StartAttempt): Attempt => {
    const { authorization_url: unused, ...view } = attempt;
    return attemptSchema.parse(view);
  };

  private invalidateAttempt = (id: string): void => {
    const attempt = this.attempts.get(id);
    if (attempt && !isTerminalAttempt(attempt)) this.attempts.set(id, { ...attempt, status: 'cancelled' });
  };
}
