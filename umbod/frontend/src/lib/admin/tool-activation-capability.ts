export type ToolActivationChange = {
  toolId: string;
  activationStatus?: 'enabled' | 'disabled';
  invocationMode?: 'direct' | 'ask';
  expectedPolicyRevision?: number;
};

export interface ToolActivationCapability<TResult = unknown> {
  saveActivations(connectorId: string, changes: ToolActivationChange[]): Promise<TResult>;
}
