import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { strFromU8, unzipSync } from 'fflate';
import { describe, expect, test } from 'vitest';
import { BrowserCodexPluginPackager } from './browser-package';
import { CodexPluginRequestSchema, normalizePluginEndpoint } from './contracts';

describe('Codex browser package', (): void => {
  test.each([
    ['https://umbod.test', 'https://umbod.test/mcp'],
    ['https://umbod.test/team/mcp/', 'https://umbod.test/team/mcp'],
    ['https://umbod.test/prefix/', 'https://umbod.test/prefix/mcp'],
    ['http://localhost:8011', 'http://localhost:8011/mcp'],
    ['http://127.0.0.1:8011/mcp', 'http://127.0.0.1:8011/mcp'],
    ['http://[::1]:8011/mcp', 'http://[::1]:8011/mcp']
  ])('normalizes %s without losing deployment paths', (input: string, expected: string): void => {
    expect(normalizePluginEndpoint(input)).toBe(expected);
  });

  test.each([
    '', '/mcp', 'file:///mcp', 'https://', 'https:///umbod.test/mcp', 'https://umbod.test:invalid/mcp',
    'https://user:secret@umbod.test/mcp', 'https://user@umbod.test/mcp', 'https://@umbod.test/mcp',
    'https://umbod.test/mcp?token=secret', 'https://umbod.test/mcp?', 'https://umbod.test/mcp#',
    ' https://umbod.test/mcp', 'https://umbod.test/\nmcp', 'https://umbod.test/\u0000mcp',
    'http://umbod.test/mcp', 'http://localhost.evil.test/mcp', 'http://127.1/mcp', 'http://127.000.0.1/mcp',
    'https://${UMBOD_HOST}/mcp', 'https://umbod.test\\@other.test/mcp'
  ])('rejects unsafe endpoint %j', (endpoint: string): void => {
    expect(CodexPluginRequestSchema.safeParse({ endpoint }).success).toBe(false);
  });

  test.each(['https://umbod.test/team/mcp', 'https://umbod.test/it\'s/"quoted"/mcp'])('zips the canonical skill and exact MCP URL %s', async (endpoint: string): Promise<void> => {
    const archive = await new BrowserCodexPluginPackager().prepare({ endpoint });
    const identity = createHash('sha256').update(endpoint).digest('hex').slice(0, 12);
    const files = unzipSync(archive.bytes);
    expect(archive.marketplaceName).toBe(`umbod-${identity}`);
    expect(archive.filename).toBe(`umbod-codex-${identity}.zip`);
    expect(Object.keys(files).sort()).toEqual([
      '.agents/plugins/marketplace.json',
      'plugins/umbod/.codex-plugin/plugin.json',
      'plugins/umbod/.mcp.json',
      'plugins/umbod/LICENSE',
      'plugins/umbod/skills/umbod-connected-apps/SKILL.md'
    ]);
    const catalog = JSON.parse(strFromU8(files['.agents/plugins/marketplace.json']));
    const manifest = JSON.parse(strFromU8(files['plugins/umbod/.codex-plugin/plugin.json']));
    expect(catalog.name).toBe(`umbod-${identity}`);
    expect(catalog.plugins[0].source.path).toBe('./plugins/umbod');
    expect(manifest.skills).toBe('./skills/');
    expect(manifest.mcpServers).toBe('./.mcp.json');
    expect(JSON.parse(strFromU8(files['plugins/umbod/.mcp.json']))).toEqual({ mcpServers: { umbod: { type: 'http', url: endpoint } } });
    expect(strFromU8(files['plugins/umbod/skills/umbod-connected-apps/SKILL.md'])).toBe(
      readFileSync(new URL('../../../../../skills/integrations/umbod-connected-apps/SKILL.md', import.meta.url), 'utf-8')
    );
    expect(strFromU8(files['plugins/umbod/LICENSE'])).toBe(readFileSync(new URL('../../../../../LICENSE', import.meta.url), 'utf-8'));
  });
});
