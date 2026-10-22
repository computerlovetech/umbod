import type { z } from 'zod';
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

  async list(): Promise<z.infer<typeof downstreamMcpConnectorListSchema>> {
    const result = await this.transport.request({ method: 'GET', path: '/admin/connectors/mcp', outputSchema: downstreamMcpConnectorListSchema });
    return { connectors: result.connectors.filter((connector) => connector.authorization_mode === 'shared') };
  }

  get(connectorId: string): Promise<z.infer<typeof downstreamMcpConnectorSchema>> {
    return this.transport.request({ method: 'GET', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}`, outputSchema: downstreamMcpConnectorSchema.refine((connector) => connector.authorization_mode === 'shared') });
  }

  create(body: DownstreamMcpConnectorCreateInput): Promise<z.infer<typeof downstreamMcpConnectorSchema>> {
    return this.transport.request({ method: 'POST', path: '/admin/connectors/mcp', body, inputSchema: downstreamMcpConnectorCreateInputSchema, outputSchema: downstreamMcpConnectorSchema });
  }

  async patchMetadata(connectorId: string, body: DownstreamMcpConnectorMetadataPatch): Promise<z.infer<typeof downstreamMcpConnectorSchema>> {
    await this.get(connectorId);
    return this.transport.request({ method: 'PATCH', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}`, body, inputSchema: downstreamMcpConnectorMetadataPatchSchema, outputSchema: downstreamMcpConnectorSchema });
  }

  async putConfiguration(connectorId: string, body: DownstreamMcpConnectorConfigurationInput): Promise<z.infer<typeof downstreamMcpConnectorConfigurationSchema>> {
    await this.get(connectorId);
    return this.transport.request({ method: 'PUT', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/configuration`, body, inputSchema: downstreamMcpConnectorConfigurationInputSchema, outputSchema: downstreamMcpConnectorConfigurationSchema });
  }

  async delete(connectorId: string): Promise<void> {
    await this.get(connectorId);
    return this.transport.request<void>({ method: 'DELETE', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}` });
  }

  async discover(connectorId: string): Promise<z.infer<typeof downstreamMcpConnectorSchema>> {
    await this.get(connectorId);
    return this.transport.request({ method: 'POST', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/discoveries`, outputSchema: downstreamMcpConnectorSchema });
  }

  async prompts(connectorId: string): Promise<z.infer<typeof downstreamPromptCatalogSchema>> {
    await this.get(connectorId);
    return this.transport.request({ method: 'GET', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/prompts`, outputSchema: downstreamPromptCatalogSchema });
  }

  async resources(connectorId: string): Promise<z.infer<typeof downstreamResourceCatalogWireSchema>> {
    await this.get(connectorId);
    return this.transport.request({ method: 'GET', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/resources`, outputSchema: downstreamResourceCatalogWireSchema });
  }

  async savePromptActivations(connectorId: string, body: PromptActivationBatchRequest): Promise<z.infer<typeof promptActivationBatchResponseSchema>> {
    await this.get(connectorId);
    return this.transport.request({
      method: 'PUT',
      path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/prompts/activation`,
      body,
      inputSchema: promptActivationBatchRequestSchema,
      outputSchema: promptActivationBatchResponseSchema
    });
  }

  async saveResourceActivations(connectorId: string, body: ResourceActivationBatchRequest): Promise<z.infer<typeof resourceActivationBatchResponseSchema>> {
    await this.get(connectorId);
    return this.transport.request({
      method: 'PUT',
      path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/resources/activation`,
      body,
      inputSchema: resourceActivationBatchRequestSchema,
      outputSchema: resourceActivationBatchResponseSchema
    });
  }

  async tools(connectorId: string): Promise<z.infer<typeof downstreamMcpToolListSchema>> {
    await this.get(connectorId);
    return this.transport.request({ method: 'GET', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/tools`, outputSchema: downstreamMcpToolListSchema });
  }

  async publish(connectorId: string): Promise<z.infer<typeof downstreamMcpPublicationSchema>> {
    await this.get(connectorId);
    return this.transport.request({ method: 'PUT', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/publication`, outputSchema: downstreamMcpPublicationSchema });
  }

  async unpublish(connectorId: string): Promise<z.infer<typeof downstreamMcpPublicationSchema>> {
    await this.get(connectorId);
    return this.transport.request({ method: 'DELETE', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/publication`, outputSchema: downstreamMcpPublicationSchema });
  }

  async listActivations(connectorId: string): Promise<z.infer<typeof downstreamMcpToolActivationBatchResponseSchema>> {
    await this.get(connectorId);
    return this.transport.request({ method: 'GET', path: `/admin/connectors/mcp/${encodeURIComponent(connectorId)}/tools/activation`, outputSchema: downstreamMcpToolActivationBatchResponseSchema });
  }

  async saveActivations(connectorId: string, changes: ToolActivationChange[]): Promise<z.infer<typeof downstreamMcpToolActivationBatchResponseSchema>> {
    await this.get(connectorId);
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
