import { render } from 'svelte/server';
import { describe, expect, test, vi } from 'vitest';
import type { ToastApi } from '#lib/components/feedback/toast-state.svelte.js';
import McpSetupGuide from './McpSetupGuide.svelte';

vi.mock('#lib/components/feedback/index.js', () => ({
  useToast: (): ToastApi => ({
    success: (): number => 1, warning: (): number => 1, error: (): number => 1,
    dismiss: (): void => {}
  })
}));

describe('Getting started plugin installation', (): void => {
  test('offers instance-configured installers without separate endpoint arguments or manual guides', (): void => {
    const { body } = render(McpSetupGuide, { props: { installerBaseUrl: 'https://site.test/api/install/v1' } });
    expect(body).not.toContain('<h1');
    expect(body).toContain('aria-label="Harness setup guides"');
    expect(body).toContain('role="tablist"');
    expect(body).toContain('macOS');
    expect(body).toContain('Linux');
    expect(body).toContain('Windows');
    expect(body).toContain('curl -fsSL');
    expect(body).toContain('https://site.test/api/install/v1/codex/install.sh');
    expect(body).not.toContain('--base-url');
    expect(body).not.toContain('--expected-endpoint');
    expect(body).not.toContain('--harness');
    expect(body).not.toContain('MCP endpoint');
    expect(body).not.toContain('Manual setup');
    expect(body).not.toContain('After installation');
    for (const client of ['Other MCP clients', 'ChatGPT', 'Claude and Cowork', 'GitHub Copilot']) {
      expect(body).not.toContain(client);
    }
    for (const client of ['Claude Code', 'Codex']) {
      expect(body).toContain(client);
    }
  });
});
