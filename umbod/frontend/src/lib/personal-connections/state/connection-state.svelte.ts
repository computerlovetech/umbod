import type { PersonalConnectionsApi } from '../api';
import type { AttemptScheduler } from '../attempt-scheduler';
import { browserAttemptScheduler } from '../infrastructure/browser-attempt-scheduler';
import type { AuthorizationBrowser, AuthorizationWindow } from '../authorization-browser';
import type { PersonalConnectionController } from './port';
import { isTerminalAttempt, type AuthorizationHealth, type Attempt, type Selection, type StartAttempt } from '../domain/schemas';
import { isUnavailable, requiresSignIn, safeActionError, safeRenewalError } from './errors';

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
  loadingTools = $state(false);
  toolsNeedLoading = $state(false);
  toolsRecovery = $state(false);
  monitoring = $state(false);
  private stopScheduledCheck: (() => void) | null = null;
  private checksRemaining = 0;
  private monitoringDeadline = 0;
  private readFailures = 0;
  private statusRead: Promise<void> | null = null;
  private revision = 0;
  private active = true;
  private authorizationWindow: AuthorizationWindow | null = null;

  constructor(selection: Selection, private readonly api: PersonalConnectionsApi, private readonly authenticationLost: () => void, private readonly onChanged: () => Promise<void> = async (): Promise<void> => {}, private readonly authorizationBrowser?: AuthorizationBrowser, private readonly scheduler: AttemptScheduler = browserAttemptScheduler, private readonly automaticWorkAllowed: () => Promise<boolean> = async (): Promise<boolean> => true) {
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
    this.loadingTools = false;
    this.toolsNeedLoading = false;
    this.toolsRecovery = false;
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
    return this.renewableAuthorization && this.selection.enabled && !this.attempt && !this.busy && !this.checking && !this.needsRefresh;
  }

  get canDiscover(): boolean {
    return this.healthPhase === 'ready' && this.health?.state === 'authorized' &&
      this.selection.enabled && this.selection.has_authorization && !this.attempt && !this.busy && !this.checking && !this.needsRefresh;
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
      if (this.current(revision) && !this.error) {
        this.needsRefresh = true;
        this.error = "Couldn't refresh connectors. Check authorization status to refresh the dashboard.";
      }
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
    this.stopMonitoring();
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
    this.loadingTools = false;
    this.renewing = false;
    this.readingDetails = false;
    this.error = '';
    this.message = '';
    try {
      await operation(revision);
    } catch (error) {
      if (this.current(revision)) this.fail(error);
    } finally {
      if (this.current(revision)) {
        this.busy = false;
        this.scheduleCheck();
      }
    }
  };

  refresh = async (): Promise<void> => {
    if (this.checking || this.loadingTools) return;
    await this.run(async (revision) => {
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
  };

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

  connect = async (): Promise<void> => {
    if (!this.active || this.busy || this.checking || this.needsRefresh || this.attempt || this.renewalInProgress) return;
    const reserved = this.reserveAuthorizationWindow();
    this.authorizationWindow = reserved;
    await this.run(async (revision): Promise<void> => {
      try {
        if (!this.selection.enabled) {
          const selection = await this.api.connections.setEnablement(this.selection.connector_id, { enabled: true });
          if (!this.current(revision)) return;
          this.selection = selection;
        }
        await this.readDetails(revision);
        if (!this.current(revision) || !this.selection.enabled) return;
        if (this.health?.state === 'authorized' && this.selection.has_authorization) {
          this.closeAuthorizationWindow();
          if (!this.selection.runtime_available || this.toolsNeedLoading) await this.loadTools(revision);
          else await this.notifyChanged(revision);
          return;
        }
        if (this.renewalInProgress) return;
        await this.initiate(revision, reserved);
      } finally {
        if (this.authorizationWindow === reserved && (!this.current(revision) || !this.authorizationOpened)) this.closeAuthorizationWindow();
      }
    });
  };

  private initiate = async (revision: number, reserved: AuthorizationWindow | null): Promise<void> => {
    const started = await this.api.authorization.start(this.selection.connector_id, {});
    if (!this.current(revision)) return;
    await this.receiveAttempt(started, revision, started.authorization_url);
    if (this.current(revision) && this.attempt?.attempt_id === started.attempt_id && !isTerminalAttempt(started) && this.authorizationUrl) {
      this.authorizationOpened = this.navigateAuthorizationWindow(reserved, this.authorizationUrl);
      this.monitoring = true;
      this.checksRemaining = 300;
      this.monitoringDeadline = this.scheduler.now() + 600000;
      this.readFailures = 0;
      this.scheduleCheck();
    }
  };

  private stopMonitoring = (): void => {
    this.monitoring = false;
    this.stopScheduledCheck?.();
    this.stopScheduledCheck = null;
    this.checksRemaining = 0;
  };

  private scheduleCheck = (): void => {
    this.stopScheduledCheck?.();
    this.stopScheduledCheck = null;
    if (!this.active || !this.monitoring || !this.attempt || !this.selection.enabled) return;
    if (this.checksRemaining <= 0 || this.scheduler.now() >= this.monitoringDeadline) {
      this.monitoring = false;
      this.error = 'Automatic sign-in checks paused. Check sign-in status to continue.';
      return;
    }
    this.stopScheduledCheck = this.scheduler.schedule(async (): Promise<void> => {
      this.stopScheduledCheck = null;
      if (this.scheduler.now() >= this.monitoringDeadline) {
        this.monitoring = false;
        this.error = 'Automatic sign-in checks paused. Check sign-in status to continue.';
        return;
      }
      if (this.busy || this.checking || this.statusRead) this.scheduleCheck();
      else await this.check();
    }, Math.min(this.monitoringDeadline - this.scheduler.now(), 10000, 2000 * 2 ** this.readFailures));
  };

  start = async (): Promise<void> => {
    if (!this.selection.enabled || this.attempt || this.checking || this.renewalInProgress) return;
    await this.run(async (revision) => {
      const reserved = this.reserveAuthorizationWindow();
      this.authorizationWindow = reserved;
      try {
        await this.initiate(revision, reserved);
      } finally {
        if (this.authorizationWindow === reserved && (!this.current(revision) || !this.authorizationOpened)) this.closeAuthorizationWindow();
      }
    });
  };

  check = async (): Promise<void> => {
    const attempt = this.attempt;
    if (!attempt || this.busy || this.checking || !this.active || this.statusRead) return;
    this.stopScheduledCheck?.();
    this.stopScheduledCheck = null;
    this.checksRemaining--;
    const revision = ++this.revision;
    this.checking = true;
    this.error = '';
    try {
      const read = this.api.authorization.get(this.selection.connector_id, attempt.attempt_id);
      this.statusRead = read.then((): void => {}, (): void => {});
      const result = await read;
      this.readFailures = 0;
      if (this.current(revision)) await this.receiveAttempt(result, revision);
    } catch (error) {
      if (this.current(revision)) {
        if (requiresSignIn(error)) { this.stopMonitoring(); this.authenticationLost(); }
        else if (isUnavailable(error)) {
          this.stopMonitoring();
          this.needsRefresh = true;
          this.error = 'Sign-in status is unavailable. Check authorization status before continuing.';
          try { await this.readDetails(revision); } catch {}
          await this.notifyChanged(revision);
        } else {
          this.readFailures++;
          this.error = 'Could not check sign-in. Check sign-in status to try again.';
        }
      }
    } finally {
      this.statusRead = null;
      if (this.current(revision)) {
        this.checking = false;
        this.scheduleCheck();
      } else if (this.active && this.attempt && this.checksRemaining > 0) this.scheduleCheck();
    }
  };

  cancel = async (): Promise<void> => {
    const attempt = this.attempt;
    if (!attempt) return;
    await this.run(async (revision) => {
      this.stopMonitoring();
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
    if (attempt.status === 'completed') {
      const allowed = await this.automaticWorkAllowed();
      if (!this.current(revision)) return;
      if (!allowed) {
        this.error = 'Could not verify your account. Refresh the dashboard before continuing sign-in.';
        return;
      }
    }
    this.clearAttempt();
    this.message = `Sign-in ${attempt.status}. Saved authorization unchanged.`;
    if (attempt.status !== 'completed') return;
    this.toolsNeedLoading = true;
    this.readingDetails = true;
    try {
      await this.readDetails(revision);
      if (!this.current(revision) || !this.selection.enabled) return;
      const allowed = await this.automaticWorkAllowed();
      if (!this.current(revision)) return;
      if (!allowed) {
        this.needsRefresh = true;
        this.toolsRecovery = true;
        this.error = 'Could not verify your account. Refresh the dashboard before loading tools.';
        return;
      }
      this.message = 'Authorization saved.';
      if (this.health?.state === 'authorized' && this.selection.has_authorization) await this.loadTools(revision);
      else await this.notifyChanged(revision);
    } catch (error) {
      if (!this.current(revision)) return;
      if (requiresSignIn(error)) this.authenticationLost();
      else {
        this.needsRefresh = true;
        this.toolsRecovery = true;
        this.error = 'Authorization saved. Retry loading tools to check access and continue.';
      }
    } finally {
      if (this.current(revision)) this.readingDetails = false;
    }
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

  private loadTools = async (revision: number): Promise<void> => {
    if (!this.current(revision) || !this.selection.enabled || this.needsRefresh) return;
    this.loadingTools = true;
    try {
      await this.api.connections.discover(this.selection.connector_id, {});
      if (!this.current(revision)) return;
      this.toolsNeedLoading = false;
      this.toolsRecovery = false;
      await this.refreshAfterChange(revision, 'Discovery completed.');
    } catch (error) {
      if (!this.current(revision)) return;
      if (requiresSignIn(error)) this.authenticationLost();
      else {
        this.needsRefresh = true;
        this.toolsRecovery = true;
        this.error = 'Could not load tools. Retry loading tools to check access and try again.';
      }
    } finally {
      if (this.current(revision)) this.loadingTools = false;
    }
  };

  retryLoadingTools = async (): Promise<void> => {
    if (!this.active || !this.toolsRecovery || this.busy || this.checking || this.attempt) return;
    await this.run(async (revision): Promise<void> => {
      this.readingDetails = true;
      try {
        await this.readDetails(revision);
        if (!this.current(revision)) return;
        this.needsRefresh = false;
        if (!this.selection.enabled || this.health?.state !== 'authorized' || !this.selection.has_authorization) {
          this.toolsRecovery = false;
          return;
        }
        if (this.selection.runtime_available && !this.toolsNeedLoading) {
          this.toolsRecovery = false;
          await this.notifyChanged(revision);
          return;
        }
        await this.loadTools(revision);
      } finally {
        if (this.current(revision)) this.readingDetails = false;
      }
    }, false);
  };

  discover = async (): Promise<void> => {
    if (!this.canDiscover) return;
    await this.run(async (revision) => {
      await this.loadTools(revision);
    });
  };
}
