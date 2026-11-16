import type { SetupRequest, SetupStatus } from './domain/setup';

export interface PersonalOAuthSetupAdministration {
  status(id: string): Promise<SetupStatus>;
  discover(id: string, input: SetupRequest): Promise<SetupStatus>;
  validate(id: string, input: SetupRequest): Promise<SetupStatus>;
}
