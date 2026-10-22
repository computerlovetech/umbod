import type { CatalogueConnector } from '../domain/schemas';
import type { ConnectionState } from '$lib/personal-connections/state/connection-state.svelte';

export interface DashboardController {
  readonly phase: 'loading' | 'ready' | 'error' | 'sign-in' | 'forbidden';
  readonly refreshing: boolean;
  readonly catalogueError: string;
  readonly personalPhase: 'idle' | 'loading' | 'ready' | 'error' | 'unavailable';
  readonly connectors: readonly CatalogueConnector[];
  readonly personalCards: readonly ConnectionState[];
  refreshOnFocus(): Promise<void>;
  loadCatalogue(): Promise<void>;
  loadPersonal(): Promise<void>;
  authenticationLost(): void;
  personalCard(id: string): ConnectionState | undefined;
  dispose(): void;
}
