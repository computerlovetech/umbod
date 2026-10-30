import { z } from 'zod';
import type { GroupPermissionsInitialTarget } from '$lib/admin/group-permissions';

const targetValue = z.string().min(1).max(200).regex(/^[^\u0000-\u001F\u007F]+$/);
const targetSchema = z.object({ connectorId: targetValue, operationId: targetValue });

export type GroupPermissionsTab = 'connectors' | 'filesystem';

export class GroupPermissionsRouteState {
  constructor(private readonly location: () => URL) {}

  get activeTab(): GroupPermissionsTab {
    return this.location().pathname.endsWith('/filesystem') ? 'filesystem' : 'connectors';
  }

  get description(): string {
    return this.activeTab === 'filesystem'
      ? 'Choose a group and assign filesystem access.'
      : 'Choose a group and assign which connectors and operations its agents can access.';
  }

  get initialTarget(): GroupPermissionsInitialTarget | null {
    if (this.activeTab !== 'connectors') return null;
    const query = this.location().searchParams;
    const result = targetSchema.safeParse({ connectorId: query.get('connector'), operationId: query.get('operation') });
    return result.success ? result.data : null;
  }

  get backHref(): string | null {
    const target = this.initialTarget;
    return target ? `/admin/openapi-connectors/${encodeURIComponent(target.connectorId)}` : null;
  }
}
