import { browserTransport, type Transport } from '$lib/admin/infrastructure/transport';
import type { WorkspaceApi } from '../api';
import { ProfileRoute } from './profile-route';

export class HttpWorkspaceApi implements WorkspaceApi {
  readonly profile: ProfileRoute;

  constructor(transport: Transport) {
    this.profile = new ProfileRoute(transport);
  }
}

export function workspaceApi(request: typeof fetch = globalThis.fetch): WorkspaceApi {
  return new HttpWorkspaceApi(browserTransport({ fetch: request }));
}
