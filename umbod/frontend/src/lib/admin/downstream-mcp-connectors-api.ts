import type { Transport } from './infrastructure/transport';
import { downstreamPromptCatalogSchema, downstreamResourceCatalogWireSchema, promptActivationBatchRequestSchema, promptActivationBatchResponseSchema, resourceActivationBatchRequestSchema, resourceActivationBatchResponseSchema, type PromptActivationBatchRequest, type ResourceActivationBatchRequest } from './capability-catalogs';
import {
  downstreamMcpConnectorCreateInputSchema,
  downstreamMcpConnectorMetadataPatchSchema, downstreamMcpConnectorConfigurationInputSchema, downstreamMcpConnectorConfigurationSchema,
  downstreamMcpConnectorListSchema,
  downstreamMcpConnectorSchema,
  downstreamMcpPublicationSchema,
  downstreamMcpToolActivationBatchRequestSchema,
  downstreamMcpToolActivationBatchResponseSchema,
  downstreamMcpToolListSchema,
  type DownstreamMcpConnectorCreateInput,
  type DownstreamMcpConnectorMetadataPatch, type DownstreamMcpConnectorConfigurationInput
} from './downstream-mcp-connectors';
import type { ToolActivationCapability, ToolActivationChange } from './tool-activation-capability';

export class DownstreamMcpConnectorsRoute implements ToolActivationCapability {
  constructor(private readonly transport: Transport) {}

  list() {
    return this.transport.request({ method: 'GET', path: '/admin/connectors/mcp', outputSchema: downstreamMcpConnectorListSchema });
  }

  get(connectorId: string) {
    return this.transport.request({ method: 'GET', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}`, outputSchema: downstreamMcpConnectorSchema });
  }

  create(body: DownstreamMcpConnectorCreateInput) {
    return this.transport.request({ method: 'POST', path: '/admin/connectors/mcp', body, inputSchema: downstreamMcpConnectorCreateInputSchema, outputSchema: downstreamMcpConnectorSchema });
  }

  patchMetadata(connectorId: string, body: DownstreamMcpConnectorMetadataPatch) {
    return this.transport.request({ method: 'PATCH', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}`, body, inputSchema: downstreamMcpConnectorMetadataPatchSchema, outputSchema: downstreamMcpConnectorSchema });
  }

  putConfiguration(connectorId: string, body: DownstreamMcpConnectorConfigurationInput) {
    return this.transport.request({ method: 'PUT', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/configuration`, body, inputSchema: downstreamMcpConnectorConfigurationInputSchema, outputSchema: downstreamMcpConnectorConfigurationSchema });
  }

  delete(connectorId: string) {
    return this.transport.request({ method: 'DELETE', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}` });
  }

  discover(connectorId: string) {
    return this.transport.request({ method: 'POST', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/discoveries`, outputSchema: downstreamMcpConnectorSchema });
  }

  prompts(connectorId: string) {
    return this.transport.request({ method: 'GET', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/prompts`, outputSchema: downstreamPromptCatalogSchema });
  }

  resources(connectorId: string) {
    return this.transport.request({ method: 'GET', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/resources`, outputSchema: downstreamResourceCatalogWireSchema });
  }

  savePromptActivations(connectorId: string, body: PromptActivationBatchRequest) {
    return this.transport.request({
      method: 'PUT',
      path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/prompts/activation`,
      body,
      inputSchema: promptActivationBatchRequestSchema,
      outputSchema: promptActivationBatchResponseSchema
    });
  }

  saveResourceActivations(connectorId: string, body: ResourceActivationBatchRequest) {
    return this.transport.request({
      method: 'PUT',
      path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/resources/activation`,
      body,
      inputSchema: resourceActivationBatchRequestSchema,
      outputSchema: resourceActivationBatchResponseSchema
    });
  }

  tools(connectorId: string) {
    return this.transport.request({ method: 'GET', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/tools`, outputSchema: downstreamMcpToolListSchema });
  }

  publish(connectorId: string) {
    return this.transport.request({ method: 'PUT', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/publication`, outputSchema: downstreamMcpPublicationSchema });
  }

  unpublish(connectorId: string) {
    return this.transport.request({ method: 'DELETE', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/publication`, outputSchema: downstreamMcpPublicationSchema });
  }

  listActivations(connectorId: string) {
    return this.transport.request({ method: 'GET', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/tools/activation`, outputSchema: downstreamMcpToolActivationBatchResponseSchema });
  }

  saveActivations(connectorId: string, changes: ToolActivationChange[]) {
    const body = {
      tools: changes.map((change) => ({
        tool_id: change.toolId,
        activation_status: change.activationStatus,
        invocation_mode: change.invocationMode,
        expected_policy_revision: change.expectedPolicyRevision
      }))
    };
    return this.transport.request({ method: 'PUT', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/tools/activation`, body, inputSchema: downstreamMcpToolActivationBatchRequestSchema, outputSchema: downstreamMcpToolActivationBatchResponseSchema });
  }
}
