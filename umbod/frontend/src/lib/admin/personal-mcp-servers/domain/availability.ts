import type { InstanceConfiguration } from '$lib/admin/instance-configuration';

export type Availability = 'enabled' | 'disabled' | 'unknown';
export type PersonalServerAvailability = { registration: Availability; authorization: Availability };

export function personalServerAvailability(configuration: InstanceConfiguration): PersonalServerAvailability {
  const groups = configuration.groups.filter((group) => group.id === 'personal_connections');
  const resolve = (variable: string): Availability => {
    if (groups.length !== 1) return 'unknown';
    const entries = groups[0].entries.filter((entry) => entry.variable === variable);
    if (entries.length !== 1 || entries[0].type !== 'boolean' || typeof entries[0].value !== 'boolean') return 'unknown';
    return entries[0].value ? 'enabled' : 'disabled';
  };
  return {
    registration: resolve('UMBOD_PERSONAL_CONNECTIONS_ENABLED'),
    authorization: resolve('UMBOD_PERSONAL_CONNECTIONS_OAUTH_ENABLED')
  };
}
