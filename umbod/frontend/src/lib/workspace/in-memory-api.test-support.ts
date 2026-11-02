import type { WorkspaceApi, WorkspaceProfileSource } from './api';
import { workspaceProfileSchema, type WorkspaceProfile } from './domain/profile';

export class InMemoryWorkspaceApi implements WorkspaceApi {
  readonly profile: WorkspaceProfileSource;

  constructor(outcome: WorkspaceProfile | Error) {
    this.profile = {
      get: async (): Promise<WorkspaceProfile> => {
        if (outcome instanceof Error) throw outcome;
        return workspaceProfileSchema.parse(outcome);
      }
    };
  }
}
