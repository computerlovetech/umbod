import { describe, expect, it } from 'vitest';
import {
  EnvironmentRuntimeConfigurationProvider,
  InMemoryRuntimeConfigurationProvider,
  type RuntimeConfiguration,
  type RuntimeConfigurationProvider
} from './runtime-configuration';

function readConfiguration(provider: RuntimeConfigurationProvider): RuntimeConfiguration {
  return provider.get();
}

describe('runtime configuration provider', () => {
  it.each([
    new InMemoryRuntimeConfigurationProvider({ publicMcpBaseUrl: 'https://mcp.example.com' }),
    new EnvironmentRuntimeConfigurationProvider({ PUBLIC_MCP_BASE_URL: 'https://mcp.example.com' })
  ])('provides a validated public MCP origin', (provider: RuntimeConfigurationProvider) => {
    expect(readConfiguration(provider)).toEqual({ publicMcpBaseUrl: 'https://mcp.example.com' });
  });

  it('provides local defaults when environment values are absent', () => {
    expect(readConfiguration(new EnvironmentRuntimeConfigurationProvider({}))).toEqual({
      publicMcpBaseUrl: 'http://localhost:8011'
    });
  });

  it('rejects invalid runtime origins', () => {
    const provider = new EnvironmentRuntimeConfigurationProvider({ PUBLIC_MCP_BASE_URL: 'not-a-url' });
    expect(() => readConfiguration(provider)).toThrow();
  });
});
