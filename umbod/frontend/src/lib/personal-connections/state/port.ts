import type { Attempt, AuthorizationHealth, Selection } from '../domain/schemas';

export interface PersonalConnectionController {
  readonly selection: Selection;
  readonly attempt: Attempt | null;
  readonly authorizationUrl: string;
  readonly authorizationOpened: boolean;
  readonly busy: boolean;
  readonly checking: boolean;
  readonly confirmingDisconnect: boolean;
  readonly needsRefresh: boolean;
  readonly message: string;
  readonly error: string;
  readonly health: AuthorizationHealth | null;
  readonly healthPhase: 'loading' | 'ready' | 'unavailable';
  readonly healthCheckedAt: string;
  readonly renewing: boolean;
  readonly readingDetails: boolean;
  readonly renewableAuthorization: boolean;
  readonly canRenew: boolean;
  readonly canDiscover: boolean;
  readonly cleanupBlocked: boolean;
  readonly renewalInProgress: boolean;
  dispose(): void;
  reconcileSelection(selection: Selection): Promise<void>;
  loadHealth(): Promise<void>;
  refresh(): Promise<void>;
  setEnabled(): Promise<void>;
  start(): Promise<void>;
  check(): Promise<void>;
  cancel(): Promise<void>;
  renew(): Promise<void>;
  discover(): Promise<void>;
  requestDisconnect(): void;
  keepAuthorization(): void;
  disconnect(): Promise<void>;
}
