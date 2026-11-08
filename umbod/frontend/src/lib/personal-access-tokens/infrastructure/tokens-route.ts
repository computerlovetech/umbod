import type { Transport } from '$lib/admin/infrastructure/transport';
import type { PersonalAccessTokensPort } from '../api';
import { createdTokenSchema, createTokenSchema, tokenIdSchema, tokenListSchema, type CreatedToken, type CreateToken, type TokenMetadata } from '../domain/schemas';

export class PersonalAccessTokensRoute implements PersonalAccessTokensPort {
  constructor(private readonly transport: Transport) {}
  list(): Promise<TokenMetadata[]> {
    return this.transport.request({ method: 'GET', path: '/me/personal-access-tokens', outputSchema: tokenListSchema });
  }
  create(input: CreateToken): Promise<CreatedToken> {
    return this.transport.request({ method: 'POST', path: '/me/personal-access-tokens', body: input, inputSchema: createTokenSchema, outputSchema: createdTokenSchema });
  }
  revoke(tokenId: string): Promise<void> {
    return this.transport.request({ method: 'DELETE', path: '/me/personal-access-tokens/' + tokenIdSchema.parse(tokenId) });
  }
}
