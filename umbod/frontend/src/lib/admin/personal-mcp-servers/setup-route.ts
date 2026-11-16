import type { Transport } from '../infrastructure/transport';
import type { PersonalOAuthSetupAdministration } from './setup-administration';
import { setupRequestSchema, setupStatusSchema, type SetupRequest, type SetupStatus } from './domain/setup';

export class PersonalOAuthSetupRoute implements PersonalOAuthSetupAdministration {
  constructor(private readonly transport: Transport) {}
  private path(id: string): string { return `/admin/connectors/mcp/${encodeURIComponent(id)}/personal-oauth/setup`; }
  status(id: string): Promise<SetupStatus> {
    return this.transport.request({ method: 'GET', path: this.path(id), outputSchema: setupStatusSchema.refine((status) => status.connector_id === id) });
  }
  discover(id: string, body: SetupRequest): Promise<SetupStatus> {
    return this.transport.request({ method: 'POST', path: `${this.path(id)}/discovery`, body, inputSchema: setupRequestSchema, outputSchema: setupStatusSchema.refine((status) => status.connector_id === id) });
  }
  validate(id: string, body: SetupRequest): Promise<SetupStatus> {
    return this.transport.request({ method: 'POST', path: `${this.path(id)}/validation`, body, inputSchema: setupRequestSchema, outputSchema: setupStatusSchema.refine((status) => status.connector_id === id) });
  }
}
