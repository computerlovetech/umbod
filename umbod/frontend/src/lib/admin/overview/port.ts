import type { AdminOverview } from './models';

export interface OverviewSource {
  load(): Promise<AdminOverview>;
}
