import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CreateToken } from '#lib/personal-access-tokens/domain/schemas.js';
import { AuthenticationRequiredError, HttpError } from '#lib/admin/infrastructure/transport.js';
import { InMemoryPersonalAccessTokens } from '#lib/personal-access-tokens/in-memory-api.test-support.js';
import { PersonalTokenState } from './personal-token-state.svelte';

afterEach((): void => { vi.restoreAllMocks(); });

function configured(api: InMemoryPersonalAccessTokens, copy: (value: string) => Promise<void> = async (): Promise<void> => {}): PersonalTokenState {
  const state = new PersonalTokenState(api, { writeText: copy });
  state.setTokenName('Agent logs');
  state.setAgentLogs(true);
  return state;
}

describe('token expiration', (): void => {
  it.each([7, 30, 60, 90])('calculates %s elapsed days at submission after the clock advances', async (days: number): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    let now = Date.parse('2030-03-01T12:30:00Z');
    const state = new PersonalTokenState(api, { writeText: async (): Promise<void> => {} }, (): number => now);
    const post = vi.spyOn(api, 'create');
    expect(state.expirationDays).toBe(30);
    expect(state.expirationOptions).toEqual([7, 30, 60, 90]);
    state.setExpirationDays(days);
    state.setTokenName(' Logs ');
    state.setAgentLogs(true);
    await state.load();
    now += 5 * 86_400_000;
    await state.create();
    const expected: CreateToken = {
      name: 'Logs',
      permissions: { telemetry: 'write' },
      expires_at: new Date(now + days * 86_400_000).toISOString()
    };
    expect(post).toHaveBeenCalledExactlyOnceWith(expected);
    expect(api.rows[0].expires_at).toBe(expected.expires_at);
    state.setExpirationDays(0);
    expect(state.expirationDays).toBe(days);
    expect(state.error).toContain('supported expiration');
  });
});

describe('token creation dialog', (): void => {
  it('opens only when available and resets dismissed form values and secrets', async (): Promise<void> => {
    const state = configured(new InMemoryPersonalAccessTokens());
    state.openCreate();
    expect(state.createDialogOpen).toBe(false);
    await state.load();
    state.openCreate();
    expect(state.createDialogOpen).toBe(true);
    state.setTokenName('My logs');
    state.setAgentLogs(true);
    state.setExpirationDays(7);
    await state.create();
    expect(state.issuedToken).toBe('test-only-secret');
    state.closeCreate();
    expect(state.createDialogOpen).toBe(false);
    expect(state.issuedToken).toBe('');
    state.openCreate();
    expect(state.tokenName).toBe('');
    expect(state.allowsAgentLogs).toBe(false);
    expect(state.expirationDays).toBe(30);
    state.dispose();
    expect(state.createDialogOpen).toBe(false);
    state.openCreate();
    expect(state.createDialogOpen).toBe(false);
  });

  it('requires explicit permission selection before issuing a token', async (): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    const state = new PersonalTokenState(api, { writeText: async (): Promise<void> => {} });
    await state.load();
    state.openCreate();
    state.setTokenName('Logs');
    expect(state.allowsAgentLogs).toBe(false);
    await state.create();
    expect(api.createCalls).toBe(0);
    expect(state.error).toBe('Select at least one permission.');
    state.setAgentLogs(true);
    await state.create();
    expect(api.createCalls).toBe(1);
    expect(state.issuedToken).toBe('test-only-secret');
  });

  it('keeps a pending creation mounted until the operation settles', async (): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    let complete: () => void = (): void => {};
    api.beforeCreate = (): Promise<void> => new Promise<void>((resolve) => { complete = resolve; });
    const state = configured(api);
    await state.load();
    state.openCreate();
    state.setTokenName('My logs');
    state.setAgentLogs(true);
    const creating = state.create();
    state.closeCreate();
    expect(state.createDialogOpen).toBe(true);
    complete();
    await creating;
    expect(state.tokens).toHaveLength(1);
    expect(api.listCalls).toBe(1);
    state.closeCreate();
    expect(state.issuedToken).toBe('');
  });

  it('automatically reconciles an uncertain creation without retrying the mutation', async (): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    const issue = api.create.bind(api);
    const spy = vi.spyOn(api, 'create').mockImplementationOnce(async (input: CreateToken): Promise<never> => {
      await issue(input);
      throw new Error('private response failure');
    });
    const state = configured(api);
    try {
      await state.load();
      state.openCreate();
      state.setTokenName('Created before response loss');
      state.setAgentLogs(true);
      await state.create();
      expect(state.createDialogOpen).toBe(false);
      expect(state.status).toBe('ready');
      expect(state.tokens.map((token): string => token.name)).toEqual(['Created before response loss']);
      expect(api.createCalls).toBe(1);
      expect(api.listCalls).toBe(2);
      expect(state.issuedToken).toBe('');
      expect(state.error).toContain('not confirmed');
      expect(state.error).not.toContain('private');
    } finally {
      spy.mockRestore();
    }
  });
});

describe('token deletion', (): void => {
  it('blocks duplicate deletions and preserves other rows until completion', async (): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    const state = configured(api);
    await state.load();
    await state.create();
    const tokenId = state.tokens[0].token_id;
    state.dismiss();
    await state.create();
    const revoke = api.revoke.bind(api);
    let complete: () => void = (): void => {};
    const spy = vi.spyOn(api, 'revoke').mockImplementationOnce(async (id: string): Promise<void> => {
      await new Promise<void>((resolve): void => { complete = resolve; });
      await revoke(id);
    });
    try {
      const pending = state.revoke(tokenId);
      await state.revoke(tokenId);
      expect(state.pending).toBe(true);
      expect(state.tokens).toHaveLength(2);
      expect(spy).toHaveBeenCalledTimes(1);
      complete();
      await pending;
      expect(state.pending).toBe(false);
      expect(state.tokens.map((row): string => row.token_id)).toEqual([api.rows[0].token_id]);
      expect(state.tokens[0].token_id).not.toBe(tokenId);
    } finally {
      spy.mockRestore();
    }
  });

  it.each([true, false])('reconciles deletion response failure with deletion applied=%s', async (applied: boolean): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    const state = configured(api);
    await state.load();
    await state.create();
    const tokenId = state.tokens[0].token_id;
    const revoke = api.revoke.bind(api);
    const spy = vi.spyOn(api, 'revoke').mockImplementationOnce(async (id: string): Promise<never> => {
      if (applied) await revoke(id);
      throw new Error('private response details');
    });
    try {
      await state.revoke(tokenId);
      expect(state.tokens).toHaveLength(applied ? 0 : 1);
      expect(state.status).toBe('ready');
      expect(state.pending).toBe(false);
      expect(state.error).toContain('Deletion was not confirmed');
      expect(state.error).not.toContain('private');
      expect(state.issuedToken).toBe('');
      expect(spy).toHaveBeenCalledTimes(1);
    } finally {
      spy.mockRestore();
    }
  });
});

describe('token management', (): void => {
  it('creates, copies separately and reconciles revocation', async (): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    const copied: string[] = [];
    const state = configured(api, async (value: string): Promise<void> => { copied.push(value); });
    await state.load();
    await state.create();
    expect(state.issuedToken).toBe('test-only-secret');
    expect(copied).toEqual([]);
    expect(state.tokens).toHaveLength(1);
    expect(api.listCalls).toBe(1);
    await state.copy();
    expect(copied).toEqual([state.issuedToken]);
    expect(state.copySucceeded).toBe(true);
    await state.revoke(state.tokens[0].token_id);
    expect(state.tokens).toEqual([]);
    expect(state.issuedToken).toBe('');
  });
  it.each([
    ['signin', new AuthenticationRequiredError()],
    ['forbidden', new HttpError(403, 'Forbidden', { secret: 'private' })]
  ] as const)('hides management when authorization requires %s', async (status, error): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    api.failure = error;
    const state = configured(api);
    await state.load();
    await state.create();
    expect(state.status).toBe(status);
    expect(state.canGenerate).toBe(false);
    expect(api.createCalls).toBe(0);
    expect(state.error).not.toContain('private');
  });
  it('prevents duplicates and fences a disposed issuance', async (): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    let complete: () => void = (): void => {};
    api.beforeCreate = (): Promise<void> => new Promise<void>((resolve) => { complete = resolve; });
    const state = configured(api);
    await state.load();
    const pending = state.create();
    await state.create();
    expect(state.pending).toBe(true);
    expect(api.createCalls).toBe(1);
    state.dispose();
    complete();
    await pending;
    expect(state.issuedToken).toBe('');
    expect(state.tokens).toEqual([]);
  });
  it('does not retry an uncertain mutation and recovers through explicit list loading', async (): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    const state = configured(api);
    await state.load();
    api.failure = new Error('private payload');
    await state.create();
    expect(state.status).toBe('error');
    expect(state.error).not.toContain('private');
    expect(api.createCalls).toBe(1);
    api.failure = undefined;
    await state.load();
    expect(state.status).toBe('ready');
    expect(api.createCalls).toBe(1);
  });
  it('rejects invalid inputs before issuance and keeps clipboard errors sanitized', async (): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    const state = configured(api, async (): Promise<void> => { throw new Error('private secret'); });
    await state.load();
    state.setTokenName('');
    await state.create();
    expect(api.createCalls).toBe(0);
    expect(state.error).toContain('Enter a token name');
    state.setTokenName('Agent logs');
    await state.create();
    await state.copy();
    expect(state.copySucceeded).toBe(false);
    expect(state.error).toContain('Could not copy');
    expect(state.error).not.toContain('private secret');
  });
  it('retains authorized token metadata when only deletion is forbidden', async (): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    const state = configured(api);
    await state.load();
    await state.create();
    vi.spyOn(api, 'revoke').mockRejectedValueOnce(new HttpError(403, 'Private deletion detail', null));
    const tokenId = state.tokens[0].token_id;
    await state.revoke(tokenId);
    expect(state.status).toBe('ready');
    expect(state.issuedToken).toBe('');
    expect(state.tokens.map((token): string => token.token_id)).toEqual([tokenId]);
    expect(state.error).toContain('Deletion was not confirmed');
    expect(state.error).not.toContain('Private deletion detail');
  });
  it('clears secrets and actions when management access is lost', async (): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    const state = configured(api);
    await state.load();
    await state.create();
    api.failure = new HttpError(403, 'Forbidden', null);
    await state.revoke(state.tokens[0].token_id);
    expect(state.status).toBe('forbidden');
    expect(state.issuedToken).toBe('');
    expect(state.tokens).toEqual([]);
  });
  it('does not resurrect a dismissed secret when creation completes', async (): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    let complete: () => void = (): void => {};
    api.beforeCreate = (): Promise<void> => new Promise<void>((resolve) => { complete = resolve; });
    const state = configured(api);
    await state.load();
    const pending = state.create();
    state.dismiss();
    complete();
    await pending;
    expect(state.tokens).toHaveLength(1);
    expect(state.issuedToken).toBe('');
  });
  it.each(['revoked', 'missing', 'expired'] as const)('clears the displayed secret after refresh finds its token %s', async (change): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    const copied: string[] = [];
    const state = configured(api, async (value: string): Promise<void> => { copied.push(value); });
    await state.load();
    await state.create();
    expect(state.issuedToken).toBe('test-only-secret');
    if (change === 'missing') api.rows = [];
    else if (change === 'revoked') api.rows = api.rows.map((row) => ({ ...row, status: 'revoked' }));
    else api.rows = api.rows.map((row) => ({ ...row, expires_at: '2000-01-01T00:00:00Z' }));
    await state.load();
    expect(state.issuedToken).toBe('');
    await state.copy();
    expect(copied).toEqual([]);
  });
  it('blocks another creation while the issued secret is displayed', async (): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    const state = configured(api);
    await state.load();
    await state.create();
    expect(state.issuedToken).toBe('test-only-secret');
    await state.create();
    expect(api.createCalls).toBe(1);
    state.dismiss();
    expect(state.issuedToken).toBe('');
    await state.create();
    expect(api.createCalls).toBe(2);
  });
});
