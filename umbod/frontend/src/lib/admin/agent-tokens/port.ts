import type { AgentTokenMetadata, CreateAgentTokenInput, IssuedAgentToken, RotateAgentTokenInput } from './domain/schemas';

export interface AgentTokens {
  list(): Promise<AgentTokenMetadata[]>;
  create(input: CreateAgentTokenInput): Promise<IssuedAgentToken>;
  rotate(agentId: string, input: RotateAgentTokenInput): Promise<IssuedAgentToken>;
  revoke(agentId: string): Promise<void>;
}
