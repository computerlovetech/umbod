import { SchemaValidationError, type Transport } from '../infrastructure/transport';
import {
  agentIdSchema,
  agentTokenListSchema,
  createAgentTokenSchema,
  issuedAgentTokenSchema,
  rotateAgentTokenSchema,
  type AgentTokenMetadata,
  type CreateAgentTokenInput,
  type IssuedAgentToken,
  type RotateAgentTokenInput
} from './domain/schemas';
import type { AgentTokens } from './port';

const path = '/admin/tokens/agents';

function agentPath(agentId: string): string {
  const parsed = agentIdSchema.safeParse(agentId);
  if (!parsed.success) throw new SchemaValidationError('outbound', parsed.error.issues);
  return `${path}/${parsed.data}`;
}

export class AgentTokensRoute implements AgentTokens {
  constructor(private readonly transport: Transport) {}

  list(): Promise<AgentTokenMetadata[]> {
    return this.transport.request({ method: 'GET', path, outputSchema: agentTokenListSchema });
  }

  create(input: CreateAgentTokenInput): Promise<IssuedAgentToken> {
    return this.transport.request({
      method: 'POST',
      path,
      requestBody: { kind: 'json', value: input, schema: createAgentTokenSchema },
      outputSchema: issuedAgentTokenSchema
    });
  }

  async rotate(agentId: string, input: RotateAgentTokenInput): Promise<IssuedAgentToken> {
    return this.transport.request({
      method: 'POST',
      path: `${agentPath(agentId)}/rotate`,
      requestBody: { kind: 'json', value: input, schema: rotateAgentTokenSchema },
      outputSchema: issuedAgentTokenSchema
    });
  }

  async revoke(agentId: string): Promise<void> {
    return this.transport.request({ method: 'DELETE', path: agentPath(agentId) });
  }
}
