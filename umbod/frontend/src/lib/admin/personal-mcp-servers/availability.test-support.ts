import type { InstanceConfiguration } from '$lib/admin/instance-configuration';

export function configurationFixture(registration: boolean = true, authorization: boolean = true): InstanceConfiguration {
  return { groups: [{ id: 'personal_connections', label: 'Personal connections', entries: [
    { variable: 'UMBOD_PERSONAL_CONNECTIONS_ENABLED', label: 'Enabled', description: '', type: 'boolean', value: registration },
    { variable: 'UMBOD_PERSONAL_CONNECTIONS_OAUTH_ENABLED', label: 'OAuth', description: '', type: 'boolean', value: authorization }
  ] }] };
}
