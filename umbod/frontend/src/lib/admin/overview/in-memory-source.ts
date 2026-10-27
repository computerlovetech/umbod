import type { OverviewSource } from './port';
import { adminOverviewSchema, type AdminOverview } from './models';

export class InMemoryOverviewSource implements OverviewSource {
  constructor(private readonly overview: AdminOverview) {}

  async load(): Promise<AdminOverview> {
    return adminOverviewSchema.parse(this.overview);
  }
}
