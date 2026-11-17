import { z } from 'zod';
import type { GroupPermissionsInitialTarget } from '#lib/admin/group-permissions.js';

const targetValue = z.string().min(1).max(200).regex(/^[^\u0000-\u001F\u007F]+$/);
const targetSchema = z.object({ connectorId: targetValue, operationId: targetValue });

export type GroupPermissionsTab = 'connectors' | 'filesystem';

export class GroupPermissionsRouteState {
  constructor(private readonly location: () => URL) {}

  get activeTab(): GroupPermissionsTab {
    return this.location().pathname.endsWith('/filesystem') ? 'filesystem' : 'connectors';
  }

  get description(): string {
    return 'Choose a group to manage connector permissions and shared namespace access.';
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
