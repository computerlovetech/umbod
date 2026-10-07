import { render } from 'svelte/server';
import { describe, expect, it, vi } from 'vitest';
import InstanceConfigurationView from './InstanceConfigurationView.svelte';

vi.mock('$lib/components/feedback', () => ({ useToast: (): object => ({ success: vi.fn(), error: vi.fn() }) }));

describe('instance settings view', () => {
  it('renders a read-only task view with collapsed technical and deployment details', () => {
    const { body } = render(InstanceConfigurationView, { props: { state: { status: 'ready', configuration: { groups: [{ id: 'runtime', label: 'Runtime', entries: [
      { variable: 'UMBOD_APP_NAME', label: 'Application name', description: 'Server name explanation', type: 'string', value: 'Team instance' },
      { variable: 'UMBOD_PUBLIC_MCP_ORIGIN', label: 'MCP origin', description: 'Server address explanation', type: 'string', value: 'https://mcp.example.com' }
    ] }] } } } });
    expect(body).toContain('Instance settings');
    expect(body).toContain('Read-only · Deployment managed');
    expect(body).toContain('Essentials');
    expect(body).toContain('Team instance');
    expect(body).toContain('Not available');
    expect(body).toContain('Copy address');
    expect(body).toContain('aria-label="Copy mcp address"');
    expect(body).toContain('<strong>MCP origin</strong>');
    expect(body).toContain('Server address explanation');
    expect(body.indexOf('id="section-addresses"')).toBeLessThan(body.indexOf('id="section-access"'));
    expect(body.indexOf('id="section-access"')).toBeLessThan(body.indexOf('id="section-tools"'));
    expect(body).toContain('not health or connectivity checks');
    expect(body).toContain('Advanced deployment details');
    expect(body).not.toMatch(/<details[^>]*\sopen/);
    const withoutTechnicalDetails = body.replace(/<details class="technical[\s\S]*?<\/details>/g, '');
    expect(withoutTechnicalDetails).not.toContain('UMBOD_');
    expect(body).not.toMatch(/<(input|select|textarea)\b/);
    expect(body).not.toContain('Save');
    for (const href of ['/admin/group-permissions', '/admin/connectors', '/admin/mcp-setup']) expect(body).toContain(`href="${href}"`);
  });

  it('preserves the failed state and retry route', () => {
    const { body } = render(InstanceConfigurationView, { props: { state: { status: 'failed', message: 'Unavailable', retryLabel: 'Try again' } } });
    expect(body).toContain('Unavailable');
    expect(body).toContain('Try again');
    expect(body).toContain('href="/admin/instance-configuration"');
    expect(body).not.toContain('Essentials');
  });

  it('preserves the empty state', () => {
    const { body } = render(InstanceConfigurationView, { props: { state: { status: 'empty' } } });
    expect(body).toContain('No non-secret instance configuration entries are available');
    expect(body).not.toContain('Essentials');
  });
});
