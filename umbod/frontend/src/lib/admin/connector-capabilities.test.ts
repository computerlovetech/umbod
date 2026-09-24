import { describe, expect, test } from 'vitest';
import { connectorCapabilityUrl, parseConnectorCapability } from './connector-capabilities';

describe('connector capability URL state', () => {
  test.each([
    ['tools', 'tools'],
    ['prompts', 'prompts'],
    ['resources', 'resources'],
    [null, 'tools'],
    ['unknown', 'tools']
  ] as const)('parses %s as %s', (value, expected) => {
    expect(parseConnectorCapability(value)).toBe(expected);
  });

  test('changes only the capability query parameter', () => {
    const currentUrl = new URL('https://agent.test/admin/connectors?connector=calendar&imported=true&capability=tools');
    const result = connectorCapabilityUrl(currentUrl, 'resources');

    expect(result.pathname).toBe('/admin/connectors');
    expect(result.searchParams.get('connector')).toBe('calendar');
    expect(result.searchParams.get('imported')).toBe('true');
    expect(result.searchParams.get('capability')).toBe('resources');
  });
});
