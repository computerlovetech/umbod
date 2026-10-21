import type { AuthorizationHealth, RenewalResult, Attempt, EmptyRequest, EnablementRequest, Selection, SelectionList, StartAttempt } from './domain/schemas';

export interface ConnectionsPort {
  list(): Promise<SelectionList>;
  get(connectorId: string): Promise<Selection>;
  setEnablement(connectorId: string, request: EnablementRequest): Promise<Selection>;
  disconnect(connectorId: string): Promise<void>;
  discover(connectorId: string, request: EmptyRequest): Promise<void>;
}

export interface AuthorizationPort {
  getHealth(connectorId: string): Promise<AuthorizationHealth>;
  renew(connectorId: string, request: EmptyRequest): Promise<RenewalResult>;
  start(connectorId: string, request: EmptyRequest): Promise<StartAttempt>;
  get(connectorId: string, attemptId: string): Promise<Attempt>;
  cancel(connectorId: string, attemptId: string): Promise<Attempt>;
}

export interface PersonalConnectionsApi {
  readonly connections: ConnectionsPort;
  readonly authorization: AuthorizationPort;
}
