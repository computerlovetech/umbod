export const connectorCapabilities = ['tools', 'prompts', 'resources'] as const;

export type ConnectorCapability = (typeof connectorCapabilities)[number];

export function parseConnectorCapability(value: string | null): ConnectorCapability {
  return connectorCapabilities.find((capability) => capability === value) ?? 'tools';
}

export function connectorCapabilityUrl(currentUrl: URL, capability: ConnectorCapability): URL {
  const url = new URL(currentUrl);
  url.searchParams.set('capability', capability);
  return url;
}
