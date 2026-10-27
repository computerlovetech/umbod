import { HttpError, isOperationalError, type Transport } from '../infrastructure/transport';
import type { OverviewSource } from './port';
import { adminOverviewResponseSchema, unavailableOverview, type AdminOverview } from './models';

export class OverviewRoute implements OverviewSource {
  constructor(private readonly transport: Transport) {}

  async load(): Promise<AdminOverview> {
    try {
      const { permission_groups, ...overview } = await this.transport.request({
        method: 'GET', path: '/admin/overview', outputSchema: adminOverviewResponseSchema
      });
      return { ...overview, permissionGroups: permission_groups };
    } catch (error) {
      if (error instanceof HttpError && (error.status === 401 || error.status === 403)) throw error;
      if (!isOperationalError(error)) throw error;
      return unavailableOverview();
    }
  }
}
