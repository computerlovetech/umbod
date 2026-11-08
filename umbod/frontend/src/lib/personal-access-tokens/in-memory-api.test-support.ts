import type { PersonalAccessTokensApi, PersonalAccessTokensPort } from './api';
import { createTokenSchema, type CreatedToken, type CreateToken, type TokenMetadata } from './domain/schemas';

export class InMemoryPersonalAccessTokens implements PersonalAccessTokensPort, PersonalAccessTokensApi {
  readonly tokens = this;
  rows: TokenMetadata[] = [];
  failure: unknown = undefined;
  createCalls = 0;
  listCalls = 0;
  beforeCreate: () => Promise<void> = async (): Promise<void> => {};
  async list(): Promise<TokenMetadata[]> {
    this.listCalls += 1;
    if (this.failure) throw this.failure;
    return [...this.rows];
  }
  async create(input: CreateToken): Promise<CreatedToken> {
    this.createCalls += 1;
    await this.beforeCreate();
    if (this.failure) throw this.failure;
    const valid = createTokenSchema.parse(input);
    const metadata: TokenMetadata = {
      token_id: this.createCalls.toString(16).padStart(32, '0'),
      owner: { issuer: 'https://identity.example', subject: 'owner' },
      name: valid.name, audience: 'umbod:telemetry', scopes: ['telemetry:write'],
      created_at: new Date().toISOString(), expires_at: valid.expires_at, status: 'active'
    };
    this.rows.push(metadata);
    return { metadata, token: 'test-only-secret' };
  }
  async revoke(tokenId: string): Promise<void> {
    if (this.failure) throw this.failure;
    this.rows = this.rows.filter((row: TokenMetadata): boolean => row.token_id !== tokenId);
  }
}
