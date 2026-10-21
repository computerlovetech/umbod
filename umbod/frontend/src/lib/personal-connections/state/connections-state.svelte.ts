import type { PersonalConnectionsApi } from '../api';
import { ConnectionState } from './connection-state.svelte';
import { isUnavailable, requiresSignIn } from './errors';

export type ConnectionsPhase = 'loading' | 'ready' | 'unavailable' | 'sign-in' | 'error';

export class ConnectionsState {
  phase = $state<ConnectionsPhase>('loading');
  cards: ConnectionState[] = $state.raw<ConnectionState[]>([]);
  private revision = 0;
  private active = true;

  constructor(private readonly api: PersonalConnectionsApi) {}

  private clear = (): void => {
    for (const card of this.cards) card.dispose();
    this.cards = [];
  };

  authenticationLost = (): void => {
    this.revision++;
    this.clear();
    this.phase = 'sign-in';
  };

  load = async (): Promise<void> => {
    if (!this.active) return;
    const revision = ++this.revision;
    this.clear();
    this.phase = 'loading';
    try {
      const result = await this.api.connections.list();
      if (!this.active || this.revision !== revision) return;
      this.cards = result.connectors.map((selection) => new ConnectionState(selection, this.api, this.authenticationLost));
      this.phase = 'ready';
      await Promise.all(this.cards.map((card) => card.loadHealth()));
    } catch (error) {
      if (!this.active || this.revision !== revision) return;
      this.phase = requiresSignIn(error) ? 'sign-in' : isUnavailable(error) ? 'unavailable' : 'error';
    }
  };

  dispose = (): void => {
    this.active = false;
    this.revision++;
    this.clear();
  };
}
