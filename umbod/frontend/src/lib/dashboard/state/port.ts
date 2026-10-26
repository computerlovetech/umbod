import type { CatalogueConnector } from '../domain/schemas';
import type { PersonalConnectionController } from '$lib/personal-connections/state/port';

export interface DashboardController {
  readonly phase: 'loading' | 'ready' | 'error' | 'sign-in' | 'forbidden';
  readonly refreshing: boolean;
  readonly catalogueError: string;
  readonly personalPhase: 'idle' | 'loading' | 'ready' | 'error' | 'unavailable';
  readonly connectors: readonly CatalogueConnector[];
  readonly selectedId: string;
  readonly identityKey: string;
  readonly selectedConnector: CatalogueConnector | undefined;
  selectConnector(id: string): void;
  readonly personalCards: readonly PersonalConnectionController[];
  refreshOnFocus(): Promise<void>;
  loadCatalogue(): Promise<void>;
  loadPersonal(): Promise<void>;
  authenticationLost(): void;
  personalCard(id: string): PersonalConnectionController | undefined;
  dispose(): void;
}
