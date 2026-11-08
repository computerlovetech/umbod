import type { ConnectorCapability } from '$lib/admin/connector-capabilities';
import type { SubpageLink } from '$lib/components/shared/workspace/SubpageNavigation.svelte';

export type ConnectorTab = 'catalog' | 'openapi' | 'downstream-mcp';

interface ConnectorNavigation {
  readonly to: { readonly url: URL } | null;
  readonly from: { readonly url: URL } | null;
}

const destinations: readonly SubpageLink[] = [
  { id: 'catalog', label: 'Connector catalog', href: '/admin/connectors' },
  { id: 'openapi', label: 'OpenAPI connectors', href: '/admin/openapi-connectors' },
  { id: 'downstream-mcp', label: 'MCP connectors', href: '/admin/downstream-mcp-connectors' }
];

export class ConnectorTabsState {
  constructor(private readonly activeTab: () => ConnectorTab, private readonly capability: () => ConnectorCapability, private readonly navigation: () => ConnectorNavigation) {}

  get links(): readonly SubpageLink[] {
    return destinations.map((destination: SubpageLink): SubpageLink => ({ ...destination, href: `${destination.href}?capability=${this.capability()}` }));
  }

  get activeId(): string { return this.pendingDestination?.id ?? this.activeTab(); }
  get pending(): boolean { return this.pendingDestination !== undefined; }

  private get pendingDestination(): SubpageLink | undefined {
    const navigation = this.navigation();
    if (navigation.to === null || navigation.to.url.pathname === navigation.from?.url.pathname) return undefined;
    return destinations.find((destination: SubpageLink): boolean => destination.href === navigation.to?.url.pathname);
  }
}
