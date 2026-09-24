import { render } from 'svelte/server';
import { describe, expect, test } from 'vitest';
import AdminConfigurationField from './AdminConfigurationField.svelte';

describe('AdminConfigurationField', () => {
  test('renders an accessible configured secret without exposing its value', () => {
    const { body } = render(AdminConfigurationField, {
      props: {
        id: 'bearer-token',
        name: 'bearerToken',
        label: 'Bearer token',
        type: 'password',
        value: '',
        required: true,
        configuredSecret: true,
        autocomplete: 'new-password'
      }
    });

    expect(body).toMatch(/<label[^>]*for="bearer-token"[^>]*>Bearer token<\/label>/);
    expect(body).toMatch(/<input[^>]*id="bearer-token"[^>]*type="password"/);
    expect(body).not.toMatch(/<input[^>]*required/);
    expect(body).toContain('Leave blank to keep the existing secret.');
    expect(body).not.toContain('********');
  });

  test('supports generic browser validation and accessible helper contracts', () => {
    const { body } = render(AdminConfigurationField, {
      props: {
        id: 'endpoint',
        name: 'endpointUrl',
        label: 'Endpoint',
        type: 'url',
        pattern: 'https://.*',
        placeholder: 'https://example.com',
        helperText: 'Enter a secure endpoint.',
        describedBy: 'external-error',
        invalid: true
      }
    });

    expect(body).toMatch(/<input[^>]*type="url"[^>]*pattern="https:\/\/\.\*"/);
    expect(body).toContain('placeholder="https://example.com"');
    expect(body).toContain('aria-describedby="external-error endpoint-helper"');
    expect(body).toContain('aria-invalid="true"');
    expect(body).toMatch(/<p class="helper[^\"]*" id="endpoint-helper">Enter a secure endpoint.<\/p>/);
  });

  test('renders required text fields and unsupported field feedback through the same API', () => {
    const supported = render(AdminConfigurationField, {
      props: { id: 'workspace', name: 'workspace', label: 'Workspace', required: true, value: 'Acme' }
    }).body;
    const unsupported = render(AdminConfigurationField, {
      props: { id: 'region', name: 'region', label: 'Region', unsupported: true }
    }).body;

    expect(supported).toMatch(/<input[^>]*required[^>]*value="Acme"/);
    expect(unsupported).toContain('Region cannot be configured in this interface.');
    expect(unsupported).not.toContain('<input');
  });
});
