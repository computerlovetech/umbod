import { render } from 'svelte/server';
import { describe, expect, test, vi } from 'vitest';
import type { ClipboardWriter } from '$lib/admin/clipboard';
import type { ToastApi } from '$lib/components/feedback/toast-state.svelte';
import McpSetupGuide from './McpSetupGuide.svelte';
import { McpSetupState, setupPrompt } from './mcp-setup-state.svelte';

vi.mock('$lib/components/feedback', () => ({
  useToast: (): ToastApi => ({
    success: (): number => 1, warning: (): number => 1, error: (): number => 1,
    dismiss: (): void => {}
  })
}));

describe('endpoint-driven MCP setup interface', () => {
  test('compact presentation keeps endpoint visible and instructions collapsed without marketing copy or a second page heading', () => {
    const { body } = render(McpSetupGuide, { props: { mcpEndpoint: 'https://umbod.test/mcp', compact: true } });
    expect(body).toContain('https://umbod.test/mcp');
    expect(body).toContain('aria-label="Copy https://umbod.test/mcp"');
    expect(body.indexOf('https://umbod.test/mcp')).toBeLessThan(body.indexOf('<details'));
    expect(body).toContain('Client instructions</summary>');
    expect(body).not.toMatch(/<details[^>]*\sopen/);
    expect(body).not.toContain('<h1');
    expect(body).not.toContain('Give your AI tools');
    expect(body).not.toContain('Copy once, connect anywhere');
    expect(body).not.toContain('After connecting, paste this prompt');
    for (const client of ['ChatGPT', 'Claude Code', 'Claude Cowork', 'GitHub Copilot']) {
      expect(body).toContain(client);
    }
  });

  test('full presentation starts with the page title without an eyebrow label', (): void => {
    const { body } = render(McpSetupGuide, { props: { mcpEndpoint: 'https://umbod.test/mcp' } });

    expect(body).toMatch(/<h1[^>]*>Connect Umbod<\/h1>/);
    expect(body).not.toContain('admin-eyebrow');
    expect(body).not.toContain('Agent harness setup');
    expect(body).toContain('Your custom MCP endpoint');
  });

  test('configuration reads the latest endpoint and escapes it as JSON', () => {
    let endpoint = 'https://umbod.test/mcp';
    const clipboard: ClipboardWriter = { writeText: vi.fn() };
    const toast: ToastApi = { success: vi.fn(), warning: vi.fn(), error: vi.fn(), dismiss: vi.fn() };
    const state = new McpSetupState(() => endpoint, clipboard, toast);
    expect(JSON.parse(state.copilotConfiguration).servers.umbod.url).toBe(endpoint);
    endpoint = 'https://umbod.test/"next"';
    expect(JSON.parse(state.copilotConfiguration).servers.umbod.url).toBe(endpoint);
  });

  test.each([true, false])('setup prompt copy reports clipboard success %s', async (succeeds) => {
    const writeText = vi.fn<ClipboardWriter['writeText']>();
    if (succeeds) writeText.mockResolvedValue();
    else writeText.mockRejectedValue(new Error('clipboard unavailable'));
    const toast: ToastApi = { success: vi.fn(), warning: vi.fn(), error: vi.fn(), dismiss: vi.fn() };
    const state = new McpSetupState(() => '/mcp', { writeText }, toast);
    await state.copySetupPrompt();
    expect(writeText).toHaveBeenCalledWith(setupPrompt);
    expect(state.copied).toBe(succeeds);
    expect(succeeds ? toast.success : toast.error).toHaveBeenCalledOnce();
  });
});
