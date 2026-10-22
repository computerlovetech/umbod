import type { DownstreamMcpConnector } from '../downstream-mcp-connectors';
import type { PersonalPolicy, PersonalPolicyReplace, PersonalServerCreate } from './domain/schemas';

export interface PersonalServerAdministration {
  get(id: string): Promise<DownstreamMcpConnector>;
  policy(id: string): Promise<PersonalPolicy>;
  create(input: PersonalServerCreate): Promise<DownstreamMcpConnector>;
  replacePolicy(id: string, input: PersonalPolicyReplace): Promise<PersonalPolicy>;
}
