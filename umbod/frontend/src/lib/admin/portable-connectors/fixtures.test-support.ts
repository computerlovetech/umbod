import type { PortableConnectorConfiguration, PortableConnectorSummary } from './domain/schemas.js';

export const submittedConnector: PortableConnectorSummary = {
  connector_id: '6a31e80e-b646-4cb5-9b32-d59dd6281d9b',
  name: 'Configuration probe',
  description: 'A submitted connector for verifying its configuration.',
  configured: false,
  status: 'inactive'
};

export const unconfiguredConnector: PortableConnectorConfiguration = {
  connector: submittedConnector,
  fields: [
    { name: 'workspace', label: 'Workspace', required: true, min_length: 1, max_length: 80, choices: [] },
    { name: 'mode', label: 'Mode', required: true, min_length: 1, max_length: 10, choices: ['preview', 'review'] }
  ],
  configuration: null
};
