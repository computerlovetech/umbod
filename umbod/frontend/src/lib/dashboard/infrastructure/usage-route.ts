import type { Transport } from '$lib/admin/infrastructure/transport';
import type { UsagePort } from '../api';
import { personalUsageSchema, usageDaysSchema, type PersonalUsage, type UsageDays } from '../domain/usage-schemas';

export class UsageRoute implements UsagePort {
  constructor(private readonly transport: Transport) {}

  get = (days: UsageDays, signal?: AbortSignal): Promise<PersonalUsage> => this.transport.request({
    method: 'GET',
    path: `/me/usage?days=${usageDaysSchema.parse(days)}`,
    outputSchema: personalUsageSchema,
    signal
  });
}
