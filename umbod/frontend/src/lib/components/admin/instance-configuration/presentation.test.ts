import { describe, expect, it } from 'vitest';
import type { InstanceConfigurationEntry } from '$lib/admin/instance-configuration';
import { displayValues, presentConfiguration } from './presentation';

function stringEntry(variable: string, value: string = 'configured'): InstanceConfigurationEntry {
  return { variable: `UMBOD_${variable}`, label: 'Server label', description: 'Server explanation', type: 'string', value };
}

const access = ['AUTH', 'OIDC_ISSUER_URL', 'ADMIN_GROUP', 'FEATURE_MCP_ADMINISTRATOR_ENABLED'];
const tools = ['MCP_TOOL_EXPOSURE', 'MCP_CODE_EXECUTION_TIMEOUT_SECONDS', 'MCP_MAXIMUM_UPLOADED_FILE_BYTES', 'MCP_DOWNSTREAM_DISCOVERY_ENABLED', 'OPENAPI_JSON_IMPORT_MAX_BYTES', 'OPENAPI_URL_RETRIEVAL_TIMEOUT_SECONDS', 'OPENAPI_EXECUTION_READ_TIMEOUT_SECONDS'];
const addresses = ['PUBLIC_SITE_ORIGIN', 'PUBLIC_API_ORIGIN', 'PUBLIC_MCP_ORIGIN', 'CORS_ORIGINS'];
const advanced = ['MCP_PERMISSION_CLAIM', 'OIDC_CONFIG_URL', 'OIDC_CLIENT_ID', 'OIDC_AUDIENCE', 'OIDC_TENANT_ID', 'OIDC_REQUIRED_SCOPES', 'APP_NAME', 'PROFILE', 'LOG_LEVEL', 'OTLP_ENABLED', 'OTLP_ALLOW_UNAUTHENTICATED', 'OTLP_MAX_REQUEST_BYTES', 'CONNECTOR_STORE', 'MCP_DOWNSTREAM_DISCOVERY_TIMEOUT_SECONDS', 'MCP_DOWNSTREAM_REFRESH_INTERVAL_SECONDS', 'MCP_DOWNSTREAM_DISCOVERY_CONCURRENCY', 'MCP_DOWNSTREAM_DISCOVERY_JITTER_RATIO', 'MCP_DOWNSTREAM_DISCOVERY_MAXIMUM_BACKOFF_SECONDS', 'MCP_AUTH_DEBUG_ENABLED', 'MCP_STATELESS_HTTP', 'OPENAPI_EXECUTION_CONNECT_TIMEOUT_SECONDS', 'OPENAPI_EXECUTION_WRITE_TIMEOUT_SECONDS', 'OPENAPI_EXECUTION_POOL_TIMEOUT_SECONDS', 'ADMIN_JWT_HEADER', 'ADMIN_JWKS_URL', 'ADMIN_MEMBERSHIP_CLAIM', 'ADMIN_AUTHENTICATION_DEBUG_ENABLED'];

describe('instance settings presentation', () => {
  it('classifies the full catalog exactly once and retains unknown source context', () => {
    const entries = [...access, ...tools, ...addresses, ...advanced, 'FUTURE_SETTING'].map((variable): InstanceConfigurationEntry => stringEntry(variable));
    const result = presentConfiguration({ groups: [{ id: 'source', label: 'Original context', entries }] });
    expect(result.access.map((setting) => setting.entry.variable)).toEqual(access.map((variable) => `UMBOD_${variable}`));
    expect(result.tools.map((setting) => setting.entry.variable)).toEqual(tools.map((variable) => `UMBOD_${variable}`));
    expect(result.addresses.map((setting) => setting.entry.variable)).toEqual(addresses.map((variable) => `UMBOD_${variable}`));
    expect(result.advanced[0].entries.map((setting) => setting.entry.variable)).toEqual([...advanced, 'FUTURE_SETTING'].map((variable) => `UMBOD_${variable}`));
    expect(result.advanced[0].label).toBe('Original context');
    expect(result.advanced[0].entries.at(-1)).toMatchObject({ label: 'Server label', description: 'Server explanation' });
    expect([...result.access, ...result.tools, ...result.addresses, ...result.advanced.flatMap((group) => group.entries)]).toHaveLength(entries.length);
  });

  it('orders administrative settings independently of their source grouping', () => {
    const result = presentConfiguration({ groups: [{ id: 'source', label: 'Original context', entries: [...access].reverse().map((variable): InstanceConfigurationEntry => stringEntry(variable)) }] });
    expect(result.access.map((setting) => setting.entry.variable)).toEqual(access.map((variable) => `UMBOD_${variable}`));
  });

  it('does not fabricate missing essentials', () => {
    expect(presentConfiguration({ groups: [] }).essentials.map((item) => item.value)).toEqual(Array(5).fill('Not available'));
  });

  it.each([
    [stringEntry('PROFILE', 'local'), 'Local development'],
    [stringEntry('PROFILE', 'future'), 'future'],
    [stringEntry('AUTH', 'dev'), 'Development authentication'],
    [stringEntry('AUTH', 'future'), 'future'],
    [stringEntry('ADMIN_GROUP', 'admins'), 'Members of admins'],
    [stringEntry('MCP_TOOL_EXPOSURE', 'flat'), 'Direct tools only'],
    [stringEntry('MCP_TOOL_EXPOSURE', 'future'), 'future'],
    [stringEntry('APP_NAME', ''), 'Not set'],
    [{ ...stringEntry('MCP_CODE_EXECUTION_TIMEOUT_SECONDS'), type: 'number', value: 1 }, '1 second'],
    [{ ...stringEntry('MCP_CODE_EXECUTION_TIMEOUT_SECONDS'), type: 'number', value: 0 }, '0 seconds'],
    [{ ...stringEntry('MCP_MAXIMUM_UPLOADED_FILE_BYTES'), type: 'integer', value: 10485760 }, '10 MiB'],
    [{ ...stringEntry('MCP_DOWNSTREAM_DISCOVERY_JITTER_RATIO'), type: 'number', value: 0.2 }, '20%'],
    [{ ...stringEntry('FEATURE_MCP_ADMINISTRATOR_ENABLED'), type: 'boolean', value: false }, 'Disabled'],
    [{ ...stringEntry('FEATURE_MCP_ADMINISTRATOR_ENABLED'), type: 'boolean', value: true }, 'Enabled'],
    [{ ...stringEntry('CORS_ORIGINS'), type: 'string_list', value: [] }, 'None configured']
  ] satisfies [InstanceConfigurationEntry, string][])('formats %j without losing neutral values', (entry, expected) => {
    expect(displayValues(entry)).toEqual([expected]);
  });

  it('keeps list values individually readable', () => {
    expect(displayValues({ ...stringEntry('CORS_ORIGINS'), type: 'string_list', value: ['one', 'two'] })).toEqual(['one', 'two']);
  });
});
