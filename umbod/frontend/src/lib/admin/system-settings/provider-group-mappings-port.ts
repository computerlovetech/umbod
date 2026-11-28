import type { ProviderGroupMappings, ProviderGroupMappingsPatch } from './domain/provider-group-mappings';

export interface ProviderGroupMappingsAdministration {
  get(signal: AbortSignal): Promise<ProviderGroupMappings>;
  update(body: ProviderGroupMappingsPatch, signal: AbortSignal): Promise<ProviderGroupMappings>;
}
