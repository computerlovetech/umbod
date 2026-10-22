import type { DownstreamMcpConnector, DownstreamMcpConnectorSummary } from '../downstream-mcp-connectors';
import type { z } from 'zod';
import type { downstreamMcpPublicationSchema } from '../downstream-mcp-connectors';
import type { PersonalPolicy, PersonalPolicyReplace, PersonalServerCreate } from './domain/schemas';

export interface PersonalServerAdministration {
  list(): Promise<DownstreamMcpConnectorSummary[]>;
  get(id: string): Promise<DownstreamMcpConnector>;
  policy(id: string): Promise<PersonalPolicy>;
  create(input: PersonalServerCreate): Promise<DownstreamMcpConnector>;
  replacePolicy(id: string, input: PersonalPolicyReplace): Promise<PersonalPolicy>;
  publish(id: string): Promise<z.infer<typeof downstreamMcpPublicationSchema>>;
  withdraw(id: string): Promise<z.infer<typeof downstreamMcpPublicationSchema>>;
  delete(id: string): Promise<void>;
}
