import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
import { resolveWorkspaceAccess, type AdminAccess } from './admin-access';
import type { WorkspaceApi } from './api';

function identityFingerprint(identity: HeaderAccountIdentityState): string {
  return JSON.stringify(identity.kind === 'visible' ? ['visible', identity.hiddenValues.id] : ['hidden']);
}

export class WorkspaceAccessState {
  adminAccess = $state<AdminAccess | 'checking'>('checking');
  accountIdentity = $state<HeaderAccountIdentityState>({ kind: 'hidden' });
  private sourceFingerprint: string;
  private sourceEpoch = $state(0);
  private profileEpoch = $state(-1);
  private revision = 0;
  private profileReadAllowed = true;
  private disposed = false;

  constructor(
    private readonly api: WorkspaceApi,
    private readonly fallbackIdentity: () => HeaderAccountIdentityState = (): HeaderAccountIdentityState => ({ kind: 'hidden' })
  ) {
    this.sourceFingerprint = identityFingerprint(fallbackIdentity());
  }

  get effectiveAccountIdentity(): HeaderAccountIdentityState {
    const fallback = this.fallbackIdentity();
    const currentFingerprint = identityFingerprint(fallback);
    return currentFingerprint === this.sourceFingerprint && this.profileEpoch === this.sourceEpoch && this.accountIdentity.kind === 'visible'
      ? this.accountIdentity : fallback;
  }

  observeIdentitySource = (identity: HeaderAccountIdentityState): boolean => {
    const fingerprint = identityFingerprint(identity);
    if (this.disposed || fingerprint === this.sourceFingerprint) return false;
    this.sourceFingerprint = fingerprint;
    this.sourceEpoch++;
    this.revision++;
    this.profileEpoch = -1;
    this.accountIdentity = { kind: 'hidden' };
    this.adminAccess = 'checking';
    this.profileReadAllowed = identity.kind === 'visible';
    if (this.profileReadAllowed) void this.load();
    return true;
  };

  load = async (): Promise<void> => {
    if (this.disposed || !this.profileReadAllowed) return;
    const revision = ++this.revision;
    const epoch = this.sourceEpoch;
    const fingerprint = this.sourceFingerprint;
    const result = await resolveWorkspaceAccess(this.api);
    if (this.disposed || revision !== this.revision || epoch !== this.sourceEpoch
      || fingerprint !== identityFingerprint(this.fallbackIdentity())) return;
    this.adminAccess = result.adminAccess;
    this.accountIdentity = result.accountIdentity;
    this.profileEpoch = epoch;
  };

  dispose = (): void => {
    this.disposed = true;
    this.revision++;
    this.profileEpoch = -1;
    this.adminAccess = 'checking';
    this.accountIdentity = { kind: 'hidden' };
  };
}
