export const connectorSetupTypeStep = 'Type';

export const connectorSetupBranchSteps = {
  native: ['Choose connector', 'Configure', 'Check & save'],
  openapi: ['Specification', 'API server', 'Configure'],
  mcp: ['Source', 'Endpoint', 'Access', 'Configure']
} as const;

export function connectorSetupSteps(
  branch: keyof typeof connectorSetupBranchSteps,
  includesType: boolean
): readonly string[] {
  const steps = connectorSetupBranchSteps[branch];
  return includesType ? [connectorSetupTypeStep, ...steps] : steps;
}
