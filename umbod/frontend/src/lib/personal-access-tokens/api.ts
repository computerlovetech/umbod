import type { CreatedToken, CreateToken, TokenMetadata } from './domain/schemas';

export interface PersonalAccessTokensPort {
  list(): Promise<TokenMetadata[]>;
  create(input: CreateToken): Promise<CreatedToken>;
  revoke(tokenId: string): Promise<void>;
}
export interface PersonalAccessTokensApi {
  readonly tokens: PersonalAccessTokensPort;
}
