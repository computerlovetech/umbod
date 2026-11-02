import type { WorkspaceProfile } from './domain/profile';

export interface WorkspaceProfileSource {
  get(): Promise<WorkspaceProfile>;
}

export interface WorkspaceApi {
  readonly profile: WorkspaceProfileSource;
}
