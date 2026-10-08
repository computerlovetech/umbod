export type FeedbackOwner = { route: string; connectorId?: string };

export class OperationState {
  data = $state<Record<string, unknown> | null>(null);
  private owner = $state<FeedbackOwner | null>(null);
  private pathname = '';
  replace = (data: Record<string, unknown> | null, owner?: FeedbackOwner): void => {
    this.owner = owner ?? null;
    this.data = data;
  };
  forOwner = (owner: FeedbackOwner): Record<string, unknown> | null => {
    if (this.owner?.route !== owner.route || this.owner.connectorId !== owner.connectorId) return null;
    return this.data;
  };
  resetForPath = (pathname: string): void => {
    if (this.pathname !== pathname) this.replace(null);
    this.pathname = pathname;
  };
}
export const operationState = new OperationState();
