import type { ConnectorToolActivationStatus } from './connectors';

export type ToolActivationDraft = {
  operationName: string;
  activationStatus: ConnectorToolActivationStatus;
};

export type ToolActivationSaveInput = {
  connectorId: string;
  activations: ToolActivationDraft[];
};

export async function connectorIdFromRequest(request: Request): Promise<string> {
  const formData = await request.formData();
  const connectorId = formData.get('connectorId');
  return typeof connectorId === 'string' ? connectorId : '';
}

export async function toolActivationSaveRequest(request: Request): Promise<ToolActivationSaveInput> {
  const form = await request.formData();
  const activations = JSON.parse(String(form.get('toolActivations') ?? '[]')) as ToolActivationDraft[];
  return {
    connectorId: String(form.get('connectorId') ?? ''),
    activations: activations.filter(isToolActivationDraft)
  };
}

export function getSecretFields(formData: FormData): Set<string> {
  const secretFields = new Set<string>();
  const metadata = formData.get('__secret_fields');

  if (typeof metadata === 'string') {
    for (const fieldName of metadata.split(',').map((field) => field.trim())) {
      if (fieldName.length > 0) {
        secretFields.add(fieldName);
      }
    }
  }

  return secretFields;
}

export function createConfigurationBody(formData: FormData, secretFields: Set<string>): Record<string, string> {
  const configuration: Record<string, string> = {};

  for (const [key, value] of formData.entries()) {
    if (key === 'connectorId' || key.startsWith('__') || typeof value !== 'string') {
      continue;
    }

    if (secretFields.has(key) && value === '') {
      continue;
    }

    configuration[key] = value;
  }

  return configuration;
}

export function createFailureValues(formData: FormData, secretFields: Set<string>): Record<string, string> {
  const values: Record<string, string> = {};

  for (const [key, value] of formData.entries()) {
    if (key === 'connectorId' || key.startsWith('__') || typeof value !== 'string' || secretFields.has(key)) {
      continue;
    }

    values[key] = value;
  }

  return values;
}

function isToolActivationDraft(value: unknown): value is ToolActivationDraft {
  if (typeof value !== 'object' || value === null) {
    return false;
  }

  const draft = value as { operationName?: unknown; activationStatus?: unknown };
  return (
    typeof draft.operationName === 'string' &&
    (draft.activationStatus === 'enabled' || draft.activationStatus === 'disabled')
  );
}
