import type { PersonalConnectionsApi } from '../api';
import type { AuthorizationBrowser, AuthorizationWindow } from '../authorization-browser';
import type { PersonalConnectionController } from './port';
import { isTerminalAttempt, type AuthorizationHealth, type Attempt, type Selection, type StartAttempt } from '../domain/schemas';
import { requiresSignIn, safeActionError, safeRenewalError } from './errors';

export class ConnectionState implements PersonalConnectionController {
  selection: Selection;
  attempt: Attempt | null = $state.raw<Attempt | null>(null);
  authorizationUrl = $state('');
  authorizationOpened = $state(false);
  busy = $state(false);
  checking = $state(false);
  confirmingDisconnect = $state(false);
  needsRefresh = $state(false);
  message = $state('');
  error = $state('');
  health: AuthorizationHealth | null = $state.raw<AuthorizationHealth | null>(null);
  healthPhase = $state<'loading' | 'ready' | 'unavailable'>('loading');
  healthCheckedAt = $state('');
  renewing = $state(false);
  readingDetails = $state(false);
  private revision = 0;
  private active = true;
  private authorizationWindow: AuthorizationWindow | null = null;

  constructor(selection: Selection, private readonly api: PersonalConnectionsApi, private readonly authenticationLost: () => void, private readonly onChanged: () => Promise<void> = async (): Promise<void> => {}, private readonly authorizationBrowser?: AuthorizationBrowser) {
    this.selection = $state.raw(selection);
  }

  dispose = (): void => {
    this.active = false;
    this.revision++;
    this.clearAttempt();
    this.health = null;
    this.healthCheckedAt = '';
    this.healthPhase = 'loading';
    this.busy = false;
    this.checking = false;
    this.renewing = false;
    this.readingDetails = false;
    this.confirmingDisconnect = false;
    this.needsRefresh = false;
    this.message = '';
    this.error = '';
    this.selection = { ...this.selection, connector_id: '', display_name: '', capability_description: '', enabled: false, has_authorization: false, runtime_available: false };
  };

  get renewableAuthorization(): boolean {
    return this.healthPhase === 'ready' && this.health !== null &&
      (this.health.state === 'authorized' || this.health.state === 'expired') && this.health.refresh_supported;
  }

  get canRenew(): boolean {
    return this.renewableAuthorization && this.selection.enabled && !this.attempt && !this.busy && !this.needsRefresh;
  }

  get canDiscover(): boolean {
    return this.healthPhase === 'ready' && this.health?.state === 'authorized' &&
      this.selection.enabled && this.selection.has_authorization && !this.attempt && !this.busy && !this.needsRefresh;
  }

  get cleanupBlocked(): boolean {
    return (this.busy && !this.renewing && !this.readingDetails) || this.needsRefresh;
  }

  get renewalInProgress(): boolean {
    return this.healthPhase === 'ready' && this.health?.state === 'refreshing';
  }

  reconcileSelection = async (selection: Selection): Promise<void> => {
    if (!this.active || this.busy || this.checking) return;
    this.selection = selection;
    if (!selection.enabled) this.clearAttempt();
    await this.loadHealth();
  };

  loadHealth = async (): Promise<void> => {
    if (!this.active || this.busy) return;
    const revision = ++this.revision;
    this.healthPhase = 'loading';
    try {
      const health = await this.api.authorization.getHealth(this.selection.connector_id);
      if (!this.current(revision)) return;
      this.installHealth(health);
    } catch (error) {
      if (!this.current(revision)) return;
      if (requiresSignIn(error)) this.authenticationLost();
      else this.healthPhase = 'unavailable';
    }
  };

  private installHealth = (health: AuthorizationHealth): void => {
    this.health = health;
    this.healthPhase = 'ready';
    this.healthCheckedAt = new Date().toLocaleString();
  };

  private ownerRead = async <T>(read: Promise<T>, revision: number): Promise<T> => {
    try {
      return await read;
    } catch (error) {
      if (this.current(revision) && requiresSignIn(error)) this.authenticationLost();
      throw error;
    }
  };

  private readDetails = async (revision: number): Promise<void> => {
    try {
      const [selection, health] = await Promise.allSettled([
        this.ownerRead(this.api.connections.get(this.selection.connector_id), revision),
        this.ownerRead(this.api.authorization.getHealth(this.selection.connector_id), revision)
      ]);
      if (!this.current(revision)) return;
      for (const result of [selection, health]) {
        if (result.status === 'rejected' && requiresSignIn(result.reason)) throw result.reason;
      }
      if (selection.status === 'rejected') throw selection.reason;
      if (health.status === 'rejected') throw health.reason;
      this.selection = selection.value;
      this.installHealth(health.value);
      if (!selection.value.enabled) this.clearAttempt();
    } catch (error) {
      if (this.current(revision)) this.healthPhase = 'unavailable';
      throw error;
    }
  };

  renew = async (): Promise<void> => {
    if (!this.canRenew) return;
    await this.run(async (revision) => {
      this.renewing = true;
      try {
        await this.api.authorization.renew(this.selection.connector_id, {});
        if (!this.current(revision)) return;
        this.confirmingDisconnect = false;
        await this.refreshAfterChange(revision, 'Authorization renewed.');
      } catch (error) {
        if (!this.current(revision)) return;
        if (requiresSignIn(error)) this.authenticationLost();
        else {
          this.error = safeRenewalError(error);
          this.needsRefresh = true;
        }
      } finally {
        if (this.current(revision)) this.renewing = false;
      }
    });
  };

  private notifyChanged = async (revision: number): Promise<void> => {
    if (!this.current(revision)) return;
    try {
      await this.onChanged();
    } catch {
      if (this.current(revision) && !this.error) this.error = "Couldn't refresh connectors. Refresh the dashboard.";
    }
  };

  private refreshAfterChange = async (revision: number, message: string, read: () => Promise<void> = (): Promise<void> => this.readDetails(revision)): Promise<void> => {
    try {
      await read();
    } catch (error) {
      if (!this.current(revision)) return;
      if (requiresSignIn(error)) {
        this.authenticationLost();
        return;
      }
      this.needsRefresh = true;
      this.error = "Couldn't refresh personal access. Check authorization status before another action.";
    }
    if (!this.current(revision)) return;
    this.message = message;
    await this.notifyChanged(revision);
  };

  private closeAuthorizationWindow = (): void => {
    const reserved = this.authorizationWindow;
    this.authorizationWindow = null;
    this.authorizationOpened = false;
    try {
      reserved?.close();
    } catch {}
  };

  private reserveAuthorizationWindow = (): AuthorizationWindow | null => {
    try {
      return this.authorizationBrowser?.reserve() ?? null;
    } catch {
      return null;
    }
  };

  private navigateAuthorizationWindow = (reserved: AuthorizationWindow | null, url: string): boolean => {
    try {
      return reserved?.navigate(url) ?? false;
    } catch {
      return false;
    }
  };

  private clearAttempt = (): void => {
    this.closeAuthorizationWindow();
    this.attempt = null;
    this.authorizationUrl = '';
    this.authorizationOpened = false;
  };

  private current = (revision: number): boolean => this.active && revision === this.revision;

  private fail = (error: unknown): void => {
    if (requiresSignIn(error)) {
      this.authenticationLost();
      return;
    }
    this.error = safeActionError(error);
    this.needsRefresh = true;
  };

  private run = async (operation: (revision: number) => Promise<void>, mutation = true, supersede = false): Promise<void> => {
    if (!this.active || (!supersede && this.busy) || (mutation && this.needsRefresh)) return;
    const revision = ++this.revision;
    this.busy = true;
    if (this.healthPhase === 'loading') this.healthPhase = 'unavailable';
    this.checking = false;
    this.renewing = false;
    this.readingDetails = false;
    this.error = '';
    this.message = '';
    try {
      await operation(revision);
    } catch (error) {
      if (this.current(revision)) this.fail(error);
    } finally {
      if (this.current(revision)) this.busy = false;
    }
  };

  refresh = async (): Promise<void> => this.run(async (revision) => {
    this.readingDetails = true;
    try {
      await this.readDetails(revision);
      if (!this.current(revision)) return;
      this.needsRefresh = false;
      this.message = 'Authorization status checked.';
    } finally {
      if (this.current(revision)) this.readingDetails = false;
      await this.notifyChanged(revision);
    }
  }, false);

  setEnabled = async (): Promise<void> => this.run(async (revision) => {
    const enabled = !this.selection.enabled;
    if (!enabled) this.clearAttempt();
    const selection = await this.api.connections.setEnablement(this.selection.connector_id, { enabled });
    if (!this.current(revision)) return;
    this.selection = selection;
    await this.refreshAfterChange(revision, enabled ? 'Personal access enabled.' : 'Personal access disabled.', async (): Promise<void> => {
      try {
        const health = await this.api.authorization.getHealth(this.selection.connector_id);
        if (this.current(revision)) this.installHealth(health);
      } catch (error) {
        if (this.current(revision)) this.healthPhase = 'unavailable';
        throw error;
      }
    });
  }, true, this.selection.enabled && (this.renewing || this.readingDetails));

  start = async (): Promise<void> => {
    if (!this.selection.enabled || this.attempt || this.renewalInProgress) return;
    await this.run(async (revision) => {
      const reserved = this.reserveAuthorizationWindow();
      this.authorizationWindow = reserved;
      try {
        const started = await this.api.authorization.start(this.selection.connector_id, {});
        if (!this.current(revision)) return;
        await this.receiveAttempt(started, revision, started.authorization_url);
        if (this.current(revision) && this.attempt?.attempt_id === started.attempt_id && !isTerminalAttempt(started) && this.authorizationUrl) {
          this.authorizationOpened = this.navigateAuthorizationWindow(reserved, this.authorizationUrl);
        }
      } finally {
        if (this.authorizationWindow === reserved && (!this.current(revision) || !this.authorizationOpened)) this.closeAuthorizationWindow();
      }
    });
  };

  check = async (): Promise<void> => {
    const attempt = this.attempt;
    if (!attempt || this.busy || this.checking || !this.active) return;
    const revision = ++this.revision;
    this.checking = true;
    this.error = '';
    try {
      const result = await this.api.authorization.get(this.selection.connector_id, attempt.attempt_id);
      if (this.current(revision)) await this.receiveAttempt(result, revision);
    } catch (error) {
      if (this.current(revision)) this.fail(error);
    } finally {
      if (this.current(revision)) this.checking = false;
    }
  };

  cancel = async (): Promise<void> => {
    const attempt = this.attempt;
    if (!attempt) return;
    await this.run(async (revision) => {
      this.closeAuthorizationWindow();
      const result = await this.api.authorization.cancel(this.selection.connector_id, attempt.attempt_id);
      if (this.current(revision)) await this.receiveAttempt(result, revision);
    });
  };

  private receiveAttempt = async (attempt: Attempt, revision: number, url?: StartAttempt['authorization_url']): Promise<void> => {
    if (!isTerminalAttempt(attempt)) {
      this.attempt = { attempt_id: attempt.attempt_id, status: attempt.status, expires_at: attempt.expires_at };
      if (url) this.authorizationUrl = url;
      return;
    }
    this.clearAttempt();
    this.message = `Sign-in ${attempt.status}. Saved authorization unchanged.`;
    if (attempt.status !== 'completed') return;
    await this.refreshAfterChange(revision, 'Authorization saved.');
  };

  requestDisconnect = (): void => {
    if (!this.cleanupBlocked) this.confirmingDisconnect = true;
  };

  keepAuthorization = (): void => {
    this.confirmingDisconnect = false;
  };

  disconnect = async (): Promise<void> => {
    if (!this.confirmingDisconnect) return;
    await this.run(async (revision) => {
      this.confirmingDisconnect = false;
      this.clearAttempt();
      await this.api.connections.disconnect(this.selection.connector_id);
      if (!this.current(revision)) return;
      await this.refreshAfterChange(revision, 'Disconnected. Authorization removed and personal access disabled.', async (): Promise<void> => {
        const result = await this.api.connections.list();
        if (!this.current(revision)) return;
        const selection = result.connectors.find((item) => item.connector_id === this.selection.connector_id);
        if (!selection) throw new Error('MCP server unavailable');
        this.selection = selection;
        this.installHealth({ state: 'not_authorized' });
      });
    }, true, this.renewing || this.readingDetails);
  };

  discover = async (): Promise<void> => {
    if (!this.canDiscover) return;
    await this.run(async (revision) => {
      await this.api.connections.discover(this.selection.connector_id, {});
      if (!this.current(revision)) return;
      await this.refreshAfterChange(revision, 'Discovery completed.');
    });
  };
}
