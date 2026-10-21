import type { Transport } from '$lib/admin/infrastructure/transport';
import type { AuthorizationPort } from '../api';
import { authorizationHealthSchema, renewalResultSchema, type AuthorizationHealth, type RenewalResult, attemptSchema, emptyRequestSchema, startAttemptSchema, type Attempt, type EmptyRequest, type StartAttempt } from '../domain/schemas';
import { connectionPath } from './connections-route';

export class AuthorizationRoute implements AuthorizationPort {
  constructor(private readonly transport: Transport) {}
  getHealth = (id: string): Promise<AuthorizationHealth> => this.transport.request({
    method: 'GET', path: `${connectionPath(id)}/authorization`, outputSchema: authorizationHealthSchema
  });
  renew = (id: string, body: EmptyRequest): Promise<RenewalResult> => this.transport.request({
    method: 'POST', path: `${connectionPath(id)}/authorization/refresh`, body, inputSchema: emptyRequestSchema, outputSchema: renewalResultSchema
  });
  start = (id: string, body: EmptyRequest): Promise<StartAttempt> => this.transport.request({
    method: 'POST', path: `${connectionPath(id)}/oauth/attempts`, body, inputSchema: emptyRequestSchema, outputSchema: startAttemptSchema
  });
  get = (id: string, attemptId: string): Promise<Attempt> => this.transport.request({
    method: 'GET', path: this.path(id, attemptId), outputSchema: attemptSchema
  });
  cancel = (id: string, attemptId: string): Promise<Attempt> => this.transport.request({
    method: 'DELETE', path: this.path(id, attemptId), outputSchema: attemptSchema
  });
  private path = (id: string, attemptId: string): string => `${connectionPath(id)}/oauth/attempts/${encodeURIComponent(attemptId)}`;
}
