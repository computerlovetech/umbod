import { HttpError } from '$lib/admin/infrastructure/transport';
import type { PersonalConnectionsApi } from '$lib/personal-connections/api';
import { ConnectionState } from '$lib/personal-connections/state/connection-state.svelte';
import { isUnavailable, requiresSignIn } from '$lib/personal-connections/state/errors';
import type { DashboardApi } from '../api';
import type { CatalogueConnector } from '../domain/schemas';
import type { DashboardController } from './port';

export class DashboardState implements DashboardController {
  phase = $state<'loading' | 'ready' | 'error' | 'sign-in' | 'forbidden'>('loading');
  personalPhase = $state<'idle' | 'loading' | 'ready' | 'error' | 'unavailable'>('idle');
  refreshing = $state(false);
  catalogueError = $state('');
  connectors = $state.raw<CatalogueConnector[]>([]);
  personalCards = $state.raw<ConnectionState[]>([]);
  private identityKey = '';
  private active = true;
  private revision = 0;
  private personalRevision = 0;
  private request: AbortController | undefined;

  constructor(
    private readonly api: DashboardApi,
    private readonly personalApi: PersonalConnectionsApi
  ) {}

  private clearPersonal = (): void => {
    this.personalRevision++;
    for (const card of this.personalCards) card.dispose();
    this.personalCards = [];
    this.personalPhase = 'idle';
  };

  authenticationLost = (): void => {
    this.revision++;
    this.request?.abort();
    this.clearPersonal();
    this.connectors = [];
    this.identityKey = '';
    this.refreshing = false;
    this.catalogueError = '';
    this.phase = 'sign-in';
  };

  personalCard = (id: string): ConnectionState | undefined =>
    this.personalCards.find((card) => card.selection.connector_id === id);

  refreshOnFocus = async (): Promise<void> => {
    if (this.phase === 'ready' && !this.refreshing) await this.loadCatalogue();
  };

  loadCatalogue = async (): Promise<void> => {
    if (!this.active) return;
    const revision = ++this.revision;
    const hadCatalogue = this.phase === 'ready';
    this.catalogueError = '';
    this.personalRevision++;
    this.request?.abort();
    const request = new AbortController();
    this.request = request;
    if (this.phase !== 'ready') this.phase = 'loading';
    this.refreshing = true;
    try {
      const result = await this.api.catalogue.list(request.signal);
      if (!this.active || revision !== this.revision) return;
      if (this.identityKey !== result.identity_key) this.clearPersonal();
      this.identityKey = result.identity_key;
      this.connectors = result.connectors;
      this.phase = 'ready';
      const personalIds = new Set(result.connectors.filter((entry) => entry.ownership === 'personal').map((entry) => entry.connector_id));
      const retained = this.personalCards.filter((card) => personalIds.has(card.selection.connector_id));
      for (const card of this.personalCards) if (!retained.includes(card)) card.dispose();
      this.personalCards = retained;
      if (result.personal_enabled && personalIds.size > 0) {
        await this.loadPersonal();
      } else {
        this.clearPersonal();
      }
    } catch (error) {
      if (!this.active || revision !== this.revision) return;
      if (requiresSignIn(error)) this.authenticationLost();
      else if (error instanceof HttpError && error.status === 403) {
        this.connectors = [];
        this.clearPersonal();
        this.phase = 'forbidden';
      } else if (hadCatalogue) {
        this.catalogueError = "Couldn't refresh connectors";
      } else {
        this.connectors = [];
        this.phase = 'error';
      }
    } finally {
      if (this.active && revision === this.revision) this.refreshing = false;
    }
  };

  loadPersonal = async (): Promise<void> => {
    if (!this.active || this.phase !== 'ready') return;
    const revision = ++this.personalRevision;
    this.personalPhase = 'loading';
    try {
      const selections = await this.personalApi.connections.list();
      if (!this.active || revision !== this.personalRevision) return;
      const eligible = new Set(this.connectors.filter((entry) => entry.ownership === 'personal').map((entry) => entry.connector_id));
      const available = selections.connectors.filter((selection) => eligible.has(selection.connector_id));
      const previous = new Map(this.personalCards.map((card) => [card.selection.connector_id, card]));
      const cards = available.map((selection) =>
        previous.get(selection.connector_id) ?? new ConnectionState(selection, this.personalApi, this.authenticationLost, this.loadCatalogue)
      );
      for (const card of this.personalCards) if (!cards.includes(card)) card.dispose();
      this.personalCards = cards;
      this.personalPhase = 'ready';
      await Promise.all(available.map((selection, index) => previous.has(selection.connector_id)
        ? cards[index].reconcileSelection(selection)
        : cards[index].loadHealth()));
    } catch (error) {
      if (!this.active || revision !== this.personalRevision) return;
      if (requiresSignIn(error)) this.authenticationLost();
      else {
        if (isUnavailable(error)) {
          this.clearPersonal();
          this.personalPhase = 'unavailable';
        } else this.personalPhase = 'error';
      }
    }
  };

  dispose = (): void => {
    this.active = false;
    this.revision++;
    this.request?.abort();
    this.clearPersonal();
    this.connectors = [];
    this.identityKey = '';
    this.refreshing = false;
    this.catalogueError = '';
  };
}
