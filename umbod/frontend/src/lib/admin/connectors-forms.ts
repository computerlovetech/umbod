import type { ConnectorToolActivationStatus } from './connectors';

export type ToolActivationDraft = {
  operationName: string;
  activationStatus: ConnectorToolActivationStatus;
};

export type ToolActivationSaveInput = {
  connectorId: string;
  activations: ToolActivationDraft[];
};

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
