import type { CatalogueCapability } from '../domain/schemas';

export type CapabilityGroup = 'tools' | 'prompts' | 'resources';

export const capabilityGroups: CapabilityGroup[] = ['tools', 'prompts', 'resources'];

export const capabilityGroupLabels: Record<CapabilityGroup, string> = {
  tools: 'Tools',
  prompts: 'Prompts',
  resources: 'Resources'
};

function capabilityGroup(capability: CatalogueCapability): CapabilityGroup {
  if (capability.kind === 'tool') return 'tools';
  if (capability.kind === 'prompt') return 'prompts';
  return 'resources';
}

export class CapabilitiesState {
  activeGroup = $state<CapabilityGroup>('tools');
  search = $state('');

  constructor(private readonly readCapabilities: () => readonly CatalogueCapability[]) {}

  get counts(): Record<CapabilityGroup, number> {
    const counts = { tools: 0, prompts: 0, resources: 0 };
    for (const capability of this.readCapabilities()) counts[capabilityGroup(capability)]++;
    return counts;
  }

  get visibleCapabilities(): readonly CatalogueCapability[] {
    const query = this.search.trim().toLocaleLowerCase();
    return this.readCapabilities().filter((capability) =>
      capabilityGroup(capability) === this.activeGroup &&
      (!query || `${capability.name} ${capability.description}`.toLocaleLowerCase().includes(query))
    );
  }

  selectGroup = (group: CapabilityGroup): void => {
    this.activeGroup = group;
    this.search = '';
  };

  setSearch = (search: string): void => {
    this.search = search;
  };
}
