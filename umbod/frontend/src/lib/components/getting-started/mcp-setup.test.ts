import { render } from 'svelte/server';
import { describe, expect, test, vi } from 'vitest';
import type { ToastApi } from '$lib/components/feedback/toast-state.svelte';
import McpSetupGuide from './McpSetupGuide.svelte';
import { McpSetupState } from './mcp-setup-state.svelte';
import { resolveMcpEndpoint } from './mcp-endpoint';

vi.mock('$lib/components/feedback', () => ({
  useToast: (): ToastApi => ({
    success: (): number => 1, warning: (): number => 1, error: (): number => 1,
    dismiss: (): void => {}
  })
}));

describe('Getting started MCP instructions', () => {
  test('offers current client instructions as a section without a second page heading', (): void => {
    const { body } = render(McpSetupGuide, { props: { mcpEndpoint: 'https://umbod.test/mcp' } });
    expect(body).toContain('https://umbod.test/mcp');
    expect(body).toContain('aria-label="Copy https://umbod.test/mcp"');
    expect(body).not.toContain('<h1');
    expect(body).not.toContain('Optional: help your agent discover connected apps');
    expect(body).not.toContain('Copy setup prompt');
    expect(body).not.toContain('umbod://setup/agent-instructions');
    expect(body).toContain('Connect your harness</h2>');
    expect(body).toContain('src="/icons/openai.svg"');
    expect(body).toContain('src="/icons/anthropic.svg"');
    expect(body).toContain('codex mcp add umbod --url');
    expect(body).toContain('codex mcp login umbod');
    expect(body).toContain('claude mcp add --transport http --scope user umbod');
    expect(body).toContain('Telemetry tokens do not authenticate MCP connections.');
    expect(body).toContain('Add custom MCP server');
    expect(body).toContain('Developer mode is not required');
    expect(body).not.toContain('Security →');
    for (const client of ['ChatGPT', 'Claude Code', 'Claude and Cowork', 'GitHub Copilot', 'Codex']) {
      expect(body).toContain(client);
    }
  });

  test('configuration reads the latest endpoint and escapes JSON and shell arguments', (): void => {
    let endpoint = 'https://umbod.test/mcp';
    const state = new McpSetupState(() => endpoint);
    expect(JSON.parse(state.copilotConfiguration).mcpServers.umbod.url).toBe(endpoint);
    expect(state.codexCommand).toBe("codex mcp add umbod --url 'https://umbod.test/mcp'");
    endpoint = 'https://umbod.test/\"next\"';
    expect(JSON.parse(state.copilotConfiguration).mcpServers.umbod.url).toBe(endpoint);
    endpoint = "https://umbod.test/it's";
    expect(state.claudeCommand).toBe("claude mcp add --transport http --scope user umbod 'https://umbod.test/it'\\''s'");
  });

  test.each([
    ['https://mcp.test', 'https://mcp.test/mcp'],
    ['https://mcp.test/', 'https://mcp.test/mcp'],
    ['https://mcp.test/mcp', 'https://mcp.test/mcp'],
    ['https://mcp.test/mcp/', 'https://mcp.test/mcp'],
    ['/mcp', 'https://site.test/mcp'],
    ['/mcp/', 'https://site.test/mcp'],
    ['/agent', 'https://site.test/agent/mcp'],
    ['https://mcp.test/prefix', 'https://mcp.test/prefix/mcp']
  ])('resolves %s to an absolute endpoint without a repeated suffix', (base, expected): void => {
    expect(resolveMcpEndpoint(base, new URL('https://site.test/getting-started'))).toBe(expected);
  });
});
