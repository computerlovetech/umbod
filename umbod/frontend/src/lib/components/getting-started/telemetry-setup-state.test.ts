import { describe, expect, it, vi } from 'vitest';
import type { CreateToken } from '$lib/personal-access-tokens/domain/schemas';
import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';
import { InMemoryPersonalAccessTokens } from '$lib/personal-access-tokens/in-memory-api.test-support';
import { InMemoryTelemetrySetup } from '$lib/telemetry-setup/in-memory-api.test-support';
import { TelemetrySetupState } from './telemetry-setup-state.svelte';

function configured(api: InMemoryPersonalAccessTokens, copy: (value: string) => Promise<void> = async (): Promise<void> => {}): TelemetrySetupState {
  const state = new TelemetrySetupState(api, new InMemoryTelemetrySetup(), { writeText: copy });
  state.setTokenName('Agent logs');
  return state;
}

describe('instance-owned telemetry setup', (): void => {
  it.each(['disabled', 'not_configured'] as const)('keeps token management available when %s', async (reason): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    const source = new InMemoryTelemetrySetup();
    const state = new TelemetrySetupState(api, source, { writeText: async (): Promise<void> => {} });
    state.setTokenName('Logs');
    await state.load();
    await state.create();
    const tokenId = state.tokens[0].token_id;
    source.value = { status: 'unavailable', reason };
    await state.load();
    expect(state.status).toBe('ready');
    expect(state.canGenerate).toBe(false);
    expect(state.availabilityMessage).toContain('operator');
    expect(state.configuration).toBe('');
    await state.create();
    expect(api.createCalls).toBe(1);
    await state.revoke(tokenId);
    expect(state.tokens).toEqual([]);
  });

  it.each(['codex', 'claude-code'] as const)('uses the exact instance endpoint for %s and clears it on endpoint change', async (agent): Promise<void> => {
    const source = new InMemoryTelemetrySetup();
    source.value = { status: 'available', logs_endpoint: 'https://custom.example:9443/tenant/prefix/v1/logs' };
    const state = new TelemetrySetupState(new InMemoryPersonalAccessTokens(), source, { writeText: async (): Promise<void> => {} });
    state.setTokenName('Logs');
    state.setAgent(agent);
    await state.load();
    await state.create();
    expect(state.configuration).toContain(source.value.logs_endpoint);
    source.value = { status: 'available', logs_endpoint: 'https://other.example/v1/logs' };
    await state.load();
    expect(state.configuration).toBe('');
  });

  it.each([7, 30, 60, 90])('calculates %s elapsed days at submission after the clock advances', async (days: number): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    let now = Date.parse('2030-03-01T12:30:00Z');
    const state = new TelemetrySetupState(api, new InMemoryTelemetrySetup(), { writeText: async (): Promise<void> => {} }, (): number => now);
    expect(state.expirationDays).toBe(30);
    expect(state.expirationOptions).toEqual([7, 30, 60, 90]);
    state.setExpirationDays(days);
    state.setTokenName('Logs');
    await state.load();
    now += 5 * 86_400_000;
    await state.create();
    expect(api.rows[0].expires_at).toBe(new Date(now + days * 86_400_000).toISOString());
    state.setExpirationDays(0);
    expect(state.expirationDays).toBe(days);
    expect(state.error).toContain('supported expiration');
  });

  it('loads both sources concurrently and fences disposed setup responses', async (): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    const source = new InMemoryTelemetrySetup();
    let complete: () => void = (): void => {};
    source.beforeGet = (): Promise<void> => new Promise<void>((resolve) => { complete = resolve; });
    const state = new TelemetrySetupState(api, source, { writeText: async (): Promise<void> => {} });
    const loading = state.load();
    expect(api.listCalls).toBe(1);
    expect(source.calls).toBe(1);
    state.dispose();
    complete();
    await loading;
    expect(state.canGenerate).toBe(false);
    expect(state.tokens).toEqual([]);
  });

  it('keeps revocation available after a setup failure without exposing error details', async (): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    const source = new InMemoryTelemetrySetup();
    const state = new TelemetrySetupState(api, source, { writeText: async (): Promise<void> => {} });
    state.setTokenName('Logs');
    await state.load();
    await state.create();
    source.failure = new Error('private endpoint');
    await state.load();
    expect(state.canGenerate).toBe(false);
    expect(state.availabilityMessage).not.toContain('private');
    expect(state.configuration).toBe('');
    await state.revoke(state.tokens[0].token_id);
    expect(state.tokens).toEqual([]);
    source.failure = undefined;
    await state.load();
    expect(state.canGenerate).toBe(true);
  });

  it.each([new AuthenticationRequiredError(), new HttpError(403, 'Forbidden', null)])('clears management when setup access is lost', async (error: Error): Promise<void> => {
    const source = new InMemoryTelemetrySetup();
    const state = new TelemetrySetupState(new InMemoryPersonalAccessTokens(), source, { writeText: async (): Promise<void> => {} });
    state.setTokenName('Logs');
    await state.load();
    await state.create();
    source.failure = error;
    await state.load();
    expect(['signin', 'forbidden']).toContain(state.status);
    expect(state.tokens).toEqual([]);
    expect(state.configuration).toBe('');
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
    state.setAgent('claude-code');
    state.setExpirationDays(7);
    await state.create();
    expect(state.configuration).toContain('test-only-secret');
    state.closeCreate();
    expect(state.createDialogOpen).toBe(false);
    expect(state.configuration).toBe('');
    state.openCreate();
    expect(state.tokenName).toBe('');
    expect(state.agent).toBe('codex');
    expect(state.expirationDays).toBe(30);
    state.dispose();
    expect(state.createDialogOpen).toBe(false);
    state.openCreate();
    expect(state.createDialogOpen).toBe(false);
  });

  it('keeps a pending creation mounted until the operation settles', async (): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    let complete: () => void = (): void => {};
    api.beforeCreate = (): Promise<void> => new Promise<void>((resolve) => { complete = resolve; });
    const state = configured(api);
    await state.load();
    state.openCreate();
    state.setTokenName('My logs');
    const creating = state.create();
    state.closeCreate();
    expect(state.createDialogOpen).toBe(true);
    complete();
    await creating;
    expect(state.tokens).toHaveLength(1);
    expect(api.listCalls).toBe(1);
    state.closeCreate();
    expect(state.configuration).toBe('');
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
      await state.create();
      expect(state.createDialogOpen).toBe(false);
      expect(state.status).toBe('ready');
      expect(state.tokens.map((token): string => token.name)).toEqual(['Created before response loss']);
      expect(api.createCalls).toBe(1);
      expect(api.listCalls).toBe(2);
      expect(state.configuration).toBe('');
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
      expect(state.configuration).toBe('');
      expect(spy).toHaveBeenCalledTimes(1);
    } finally {
      spy.mockRestore();
    }
  });
});

describe('telemetry setup', (): void => {
  it('creates, copies separately and reconciles revocation', async (): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    const copied: string[] = [];
    const state = configured(api, async (value: string): Promise<void> => { copied.push(value); });
    await state.load();
    await state.create();
    expect(state.configuration).toContain('test-only-secret');
    expect(copied).toEqual([]);
    expect(state.tokens).toHaveLength(1);
    expect(api.listCalls).toBe(1);
    await state.copy();
    expect(copied).toEqual([state.configuration]);
    expect(state.copySucceeded).toBe(true);
    await state.revoke(state.tokens[0].token_id);
    expect(state.tokens).toEqual([]);
    expect(state.configuration).toBe('');
  });
  it.each([new AuthenticationRequiredError(), new HttpError(403, 'Forbidden', { secret: 'private' })])('hides management for denied identities', async (error: Error): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    api.failure = error;
    const state = configured(api);
    await state.load();
    await state.create();
    expect(['signin', 'forbidden']).toContain(state.status);
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
    expect(state.configuration).toBe('');
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
    expect(state.error).not.toContain('URL');
    state.setTokenName('Agent logs');
    await state.create();
    await state.copy();
    expect(state.copySucceeded).toBe(false);
    expect(state.error).toContain('Could not copy');
    expect(state.error).not.toContain('private secret');
  });
  it('clears secrets and actions when management access is lost', async (): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    const state = configured(api);
    await state.load();
    await state.create();
    api.failure = new HttpError(403, 'Forbidden', null);
    await state.revoke(state.tokens[0].token_id);
    expect(state.status).toBe('forbidden');
    expect(state.configuration).toBe('');
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
    expect(state.configuration).toBe('');
  });
  it.each(['revoked', 'missing', 'expired'] as const)('clears the displayed secret after refresh finds its token %s', async (change): Promise<void> => {
    const api = new InMemoryPersonalAccessTokens();
    const copied: string[] = [];
    const state = configured(api, async (value: string): Promise<void> => { copied.push(value); });
    await state.load();
    await state.create();
    expect(state.configuration).toContain('test-only-secret');
    if (change === 'missing') api.rows = [];
    else if (change === 'revoked') api.rows = api.rows.map((row) => ({ ...row, status: 'revoked' }));
    else api.rows = api.rows.map((row) => ({ ...row, expires_at: '2000-01-01T00:00:00Z' }));
    await state.load();
    expect(state.configuration).toBe('');
    await state.copy();
    expect(copied).toEqual([]);
  });
  it('clears secret on dismissal and agent change', async (): Promise<void> => {
    const state = configured(new InMemoryPersonalAccessTokens());
    await state.load();
    await state.create();
    state.dismiss();
    expect(state.configuration).toBe('');
    await state.create();
    state.setAgent('claude-code');
    expect(state.configuration).toBe('');
  });
});
