import { strFromU8, unzipSync } from 'fflate';
import { describe, expect, test, vi } from 'vitest';
import type { CreatedToken } from '#lib/personal-access-tokens/domain/schemas.js';
import type { TelemetrySetupSource } from '#lib/telemetry-setup/api.js';
import { PrepareTelemetryInstaller } from './prepare-telemetry-installer';
import type { InstallerArtifactSource } from './installer-artifact';

const now = '2026-05-01T00:00:00.000Z';
const expiry = '2026-05-31T00:00:00.000Z';
const endpoint = 'https://collector.test/v1/logs';
const tokenId = 'a'.repeat(32);
const token = `umbod_pat_v1_${tokenId}_${'b'.repeat(43)}`;
const created: CreatedToken = {
  token,
  metadata: {
    token_id: tokenId,
    owner: { issuer: 'issuer', subject: 'user' },
    name: 'Claude Code installer telemetry',
    audience: 'umbod',
    scopes: ['telemetry:write'],
    created_at: now,
    expires_at: expiry,
    status: 'active'
  }
};
const bashTemplate = '#!/usr/bin/env bash\n: "${umbod_telemetry_payload:-}"\n';
const powershellTemplate = '& {\n$null = $UmbodTelemetryPayload\n}\n';

function fixture(artifact: string, setup: TelemetrySetupSource = { get: async () => ({ status: 'available', logs_endpoint: endpoint }) }): {
  service: PrepareTelemetryInstaller;
  create: ReturnType<typeof vi.fn<() => Promise<CreatedToken>>>;
  revoke: ReturnType<typeof vi.fn<(id: string) => Promise<void>>>;
  read: ReturnType<typeof vi.fn<InstallerArtifactSource['read']>>;
} {
  const read = vi.fn<InstallerArtifactSource['read']>().mockResolvedValue(artifact);
  const create = vi.fn<() => Promise<CreatedToken>>().mockResolvedValue(created);
  const revoke = vi.fn<(id: string) => Promise<void>>().mockResolvedValue(undefined);
  const service = new PrepareTelemetryInstaller(
    (): string => 'https://umbod.test/api/install/v1',
    setup,
    { create, revoke, list: async () => [] },
    { read },
    (): number => Date.parse(now)
  );
  return { service, create, revoke, read };
}

describe('private telemetry installers', () => {
  test.each([
    ['linux', 'sh', bashTemplate],
    ['windows', 'ps1', powershellTemplate]
  ] as const)('issues a scoped token and keeps it out of executable %s source', async (platform, extension, template): Promise<void> => {
    const { service, create, read } = fixture(template);
    const result = await service.prepare(platform, 'claude-code');
    const files = unzipSync(new Uint8Array(await result.arrayBuffer()));
    const script = strFromU8(files[`umbod-install.${extension}`]);
    const encoded = strFromU8(files['umbod-telemetry.txt']).trim();
    expect(read).toHaveBeenCalledExactlyOnceWith(`https://umbod.test/api/install/v1/claude-code/install.${extension}`);
    expect(create).toHaveBeenCalledExactlyOnceWith({
      name: 'Claude Code installer telemetry', expires_at: expiry, permissions: { telemetry: 'write' }
    });
    expect(JSON.parse(atob(encoded))).toEqual({ endpoint, token });
    expect(script).toContain('umbod-telemetry.txt');
    expect(script).not.toContain(token);
    expect(script).not.toContain(encoded);
  });

  test('does not issue a token with a public installer that lacks telemetry support', async (): Promise<void> => {
    const { service, create } = fixture('#!/usr/bin/env bash\ntrue\n');
    await expect(service.prepare('macos', 'claude-code')).rejects.toThrow('does not support');
    expect(create).not.toHaveBeenCalled();
  });

  test('does not issue a token for an unsafe collector', async (): Promise<void> => {
    const { service, create } = fixture(bashTemplate, { get: async () => ({ status: 'available', logs_endpoint: 'http://collector.test/v1/logs' }) });
    await expect(service.prepare('macos', 'claude-code')).rejects.toThrow('require HTTPS');
    expect(create).not.toHaveBeenCalled();
  });

  test('revokes the issued token if the wizard changes its choice during issuance', async (): Promise<void> => {
    const { service, create, revoke } = fixture(bashTemplate);
    const controller = new AbortController();
    create.mockImplementation(async (): Promise<CreatedToken> => {
      controller.abort();
      return created;
    });
    await expect(service.prepare('macos', 'claude-code', controller.signal)).rejects.toThrow();
    expect(revoke).toHaveBeenCalledExactlyOnceWith(tokenId);
  });
});
