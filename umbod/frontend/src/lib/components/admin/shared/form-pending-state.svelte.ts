export class FormPendingState {
  pendingKeys = $state.raw<Set<string>>(new Set());

  start = (key: string): void => {
    this.pendingKeys = new Set([...this.pendingKeys, key]);
  };

  stop = (key: string): void => {
    const nextPendingKeys = new Set(this.pendingKeys);
    nextPendingKeys.delete(key);
    this.pendingKeys = nextPendingKeys;
  };

  isPending = (key: string): boolean => {
    return this.pendingKeys.has(key);
  };
}
