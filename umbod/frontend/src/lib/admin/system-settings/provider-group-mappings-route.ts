import type { Transport } from '../infrastructure/transport';
import {
  providerGroupMappingsPatchSchema,
  providerGroupMappingsSchema,
  type ProviderGroupMappings,
  type ProviderGroupMappingsPatch
} from './domain/provider-group-mappings';
import type { ProviderGroupMappingsAdministration } from './provider-group-mappings-port';

const path = '/admin/system-settings/provider-group-mappings';

export class ProviderGroupMappingsRoute implements ProviderGroupMappingsAdministration {
  constructor(private readonly transport: Transport) {}

  get(signal: AbortSignal): Promise<ProviderGroupMappings> {
    return this.transport.request({ method: 'GET', path, signal, outputSchema: providerGroupMappingsSchema });
  }

  update(body: ProviderGroupMappingsPatch, signal: AbortSignal): Promise<ProviderGroupMappings> {
    return this.transport.request({
      method: 'PATCH', path, signal,
      requestBody: { kind: 'json', value: body, schema: providerGroupMappingsPatchSchema },
      outputSchema: providerGroupMappingsSchema
    });
  }
}
