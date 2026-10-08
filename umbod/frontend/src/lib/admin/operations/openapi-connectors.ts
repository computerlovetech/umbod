import { operationFailure, operationRedirect, type BrowserOperations } from './contracts';
import { openApiSetupRequestSchema, openApiSetupCleanupFailureSchema } from '../openapi-setup';
import { z } from 'zod';

async function readCatalogFile(file: File): Promise<Record<string, unknown>> {
  if (!file.name.toLowerCase().endsWith('.json') || file.type !== 'application/json') throw new Error('Choose a .json file with the JSON content type.');
  if (file.size > OPEN_API_CATALOG_FILE_MAX_BYTES) throw new Error('The JSON file must be 10 MiB or smaller.');
  return z.record(z.string(), z.unknown()).parse(JSON.parse(await file.text()));
}
import { HttpError, isOperationalError } from '$lib/admin/infrastructure/transport';
import { approvedHostnameSchema, importOpenApiCatalogDocumentRequestSchema, openApiToolActivationBatchRequestSchema, OPEN_API_CATALOG_FILE_MAX_BYTES } from '$lib/admin/openapi-connectors';
import { createOpenApiConnector, openApiImportConflictResult, setOpenApiPublication } from '$lib/admin/openapi-connectors-api';

import { invocationPolicyBatchUpdateRequestSchema, invocationPolicyConflictResponseSchema } from '$lib/admin/invocation-policy';
import { presentSaveFailureWithReconciliation } from '$lib/admin/tool-activation-reconciliation';

function listLocation(connectorId: string, query?: Record<string, string>): string {
  const params = new URLSearchParams({ connector: connectorId, ...query });
  return `/admin/openapi-connectors?${params.toString()}`;
}

function connectorIdFromForm(data: FormData): string {
  return String(data.get('connectorId') ?? '').trim();
}

function parseApprovedHosts(data: FormData): string[] {
  const approvedHosts = data
    .getAll('approved_hosts')
    .filter((value): value is string => typeof value === 'string')
    .map((value) => value.trim().toLowerCase())
    .filter((value) => value.length > 0);
  return [...new Set(approvedHosts)];
}

function setupValues(data: FormData): {
  displayName: string;
  capabilityDescription: string;
  toolNamePrefix: string;
  connectorId: string;
  authenticationType: 'none' | 'bearer' | '';
  bearerToken: string;
  approvedHostname: string;
  importMode: 'file' | 'url';
  file: File | null;
  document: Record<string, unknown> | null;
} {
  const fileValue = data.get('file');
  const documentValue = String(data.get('document') ?? '');
  let document: Record<string, unknown> | null = null;
  if (documentValue) {
    try {
      const parsed: unknown = JSON.parse(documentValue);
      if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) document = parsed as Record<string, unknown>;
    } catch {
      document = null;
    }
  }
  return {
    displayName: String(data.get('displayName') ?? '').trim(),
    capabilityDescription: String(data.get('capabilityDescription') ?? '').trim(),
    toolNamePrefix: String(data.get('toolNamePrefix') ?? '').trim(),
    connectorId: connectorIdFromForm(data),
    authenticationType: ['none', 'bearer'].includes(String(data.get('authenticationType'))) ? String(data.get('authenticationType')) as 'none' | 'bearer' : '',
    bearerToken: String(data.get('bearerToken') ?? ''),
    approvedHostname: String(data.get('approvedHostname') ?? '').trim().toLowerCase(),
    importMode: data.get('importMode') === 'url' ? 'url' : 'file',
    file: fileValue instanceof File && fileValue.size > 0 ? fileValue : null,
    document
  };
}

function safeImportError(
  error: unknown,
  mode: 'file' | 'url',
  connectorId: string,
  preserved: { url?: string; approvedHosts?: string[] }
) {
  const conflict = openApiImportConflictResult(error);
  if (conflict) {
    return {
      status: 'conflict' as const,
      mode,
      connectorId,
      ...preserved,
      message: `Import would remove operations still granted to groups: ${conflict.removedOperationIds.join(', ')}.`,
      retryable: false,
      removedOperationIds: conflict.removedOperationIds,
      affectedGroupIds: conflict.affectedGroupIds
    };
  }
  const base = { status: 'failed' as const, mode, connectorId, ...preserved };
  if (!isOperationalError(error)) throw error;
  if (!(error instanceof HttpError)) return { ...base, message: 'Import is unavailable. Try again.', retryable: true };
  if (error.status === 413) return { ...base, message: 'The source exceeds the 10 MB import limit.', retryable: false };
  if (error.status === 415) return { ...base, message: 'Choose a .json file with the JSON content type.', retryable: false };
  if (error.status === 400 || error.status === 422) {
    return {
      ...base,
      message:
        mode === 'url'
          ? 'The retrieved OpenAPI document or approved hostnames are not valid.'
          : 'The JSON file or approved hostnames are not valid.',
      retryable: false
    };
  }
  if (error.status === 404) {
    return {
      ...base,
      status: 'stale' as const,
      message: 'This connector no longer exists. Return to the connector list.',
      retryable: false
    };
  }
  return { ...base, message: 'Import is unavailable. Try again.', retryable: true };
}

export const openApiConnectorsOperations: BrowserOperations = {
  setup: async (api, data) => {
    const values = setupValues(data);
    const hasSource = values.importMode === 'file' ? Boolean(values.file) : Boolean(values.document);
    if (!values.displayName || !values.toolNamePrefix || !values.capabilityDescription || !hasSource || !approvedHostnameSchema.safeParse(values.approvedHostname).success || !values.authenticationType || (values.authenticationType === 'bearer' && !values.bearerToken.trim())) {
      return { status: 'invalid', displayName: values.displayName, message: 'Complete all required connector setup fields.' };
    }
    let document: Record<string, unknown> | null;
    try { document = values.file ? await readCatalogFile(values.file) : values.document; }
    catch { return { status: 'invalid', message: 'Choose a valid JSON object file with JSON content type, no larger than 10 MiB.' }; }
    const input = openApiSetupRequestSchema.safeParse({ display_name: values.displayName, tool_name_prefix: values.toolNamePrefix, capability_description: values.capabilityDescription, document, approved_hosts: [values.approvedHostname], authentication_type: values.authenticationType, bearer_token: values.bearerToken });
    if (!input.success) return { status: 'invalid', message: 'Complete all required connector setup fields.' };
    try {
      const created = await api.openApiConnectors.connectors.setup(input.data);
      return operationRedirect(listLocation(created.connector_id));
    } catch (error) {
      const cleanup = error instanceof HttpError ? openApiSetupCleanupFailureSchema.safeParse(error.body) : undefined;
      if (cleanup?.success) return { status: 'warning', connectorId: cleanup.data.connector_id, retryable: false, message: `Setup failed and connector ${cleanup.data.connector_id} could not be removed. Reload the list and delete this connector before starting another setup.` };
      return safeImportError(error, values.importMode, '', { approvedHosts: [values.approvedHostname] });
    }
  },
  configure: async (api, data) => {
    const values = setupValues(data);
    if (values.file) {
      try { values.document = await readCatalogFile(values.file); values.file = null; }
      catch { return { status: 'invalid', connectorId: values.connectorId, message: 'Choose a valid JSON object file with JSON content type, no larger than 10 MiB.' }; }
    }
    const replacingCatalog = Boolean(values.document);
    if (!values.connectorId || !values.authenticationType || (replacingCatalog && !approvedHostnameSchema.safeParse(values.approvedHostname).success)) {
      return { status: 'invalid', connectorId: values.connectorId, message: 'Configuration values are invalid.' };
    }
    try {
      await api.openApiConnectors.connectors.putConfiguration(values.connectorId, { authentication_type: values.authenticationType, bearer_token: values.bearerToken });
    } catch (error) {
      return { ...safeImportError(error, values.importMode, values.connectorId, { approvedHosts: values.approvedHostname ? [values.approvedHostname] : [] }), message: 'Authentication was not saved. The existing catalog was not changed.' };
    }
    try {
      if (values.document) {
        await api.openApiConnectors.imports.importJson(values.connectorId, { document: values.document, approved_hosts: [values.approvedHostname] });
      }
    } catch (error) {
      return { ...safeImportError(error, values.importMode, values.connectorId, { approvedHosts: values.approvedHostname ? [values.approvedHostname] : [] }), message: 'Authentication was saved, but the catalog replacement failed. Review the preserved values and retry the import.' };
    }
    return operationRedirect(listLocation(values.connectorId));
  },
  create: async (api, data) => {
    const displayNameValue = data.get('displayName');
    const toolNamePrefixValue = data.get('toolNamePrefix');
    const capabilityDescriptionValue = data.get('capabilityDescription');
    const displayName = typeof displayNameValue === 'string' ? displayNameValue : '';
    const toolNamePrefix = typeof toolNamePrefixValue === 'string' ? toolNamePrefixValue : '';
    const capabilityDescription = typeof capabilityDescriptionValue === 'string' ? capabilityDescriptionValue : '';
    const result = await createOpenApiConnector(api.openApiConnectors, displayName, toolNamePrefix, capabilityDescription);
    if ('connectorId' in result) {
      if (data.get('initialCapabilityOverride') === 'on') {
        const description = String(data.get('initialCapabilityOverrideDescription') ?? '');
        await api.capabilityDescriptions.set('openapi', result.connectorId, description, 0);
      }
      return operationRedirect(listLocation(result.connectorId));
    }
    return result;
  },
  importFile: async (api, data) => {
    const connectorId = connectorIdFromForm(data);
    const files = data.getAll('file').filter((value): value is File => value instanceof File && value.size > 0);
    const approvedHosts = parseApprovedHosts(data);
    const metadata = approvedHosts.map((hostname) => approvedHostnameSchema.safeParse(hostname));
    if (!connectorId) {
      return { status: 'invalid', mode: 'file' as const, approvedHosts, message: 'Choose a connector to import into.', retryable: false };
    }
    if (files.length !== 1) {
      return {
        status: 'invalid',
        mode: 'file' as const,
        connectorId,
        approvedHosts,
        message: 'Choose exactly one JSON file.',
        retryable: false
      };
    }
    if (approvedHosts.length === 0) {
      return {
        status: 'invalid',
        mode: 'file' as const,
        connectorId,
        approvedHosts,
        message: 'Add at least one exact hostname.',
        retryable: false
      };
    }
    const file = files[0];
    if (!file.name.toLowerCase().endsWith('.json') || file.type !== 'application/json') {
      return {
        status: 'invalid',
        mode: 'file' as const,
        connectorId,
        approvedHosts,
        message: 'Choose a .json file with the JSON content type.',
        retryable: false
      };
    }
    if (file.size > OPEN_API_CATALOG_FILE_MAX_BYTES) {
      return {
        status: 'invalid',
        mode: 'file' as const,
        connectorId,
        approvedHosts,
        message: 'The JSON file must be 10 MiB or smaller.',
        retryable: false
      };
    }
    if (metadata.some((result) => !result.success)) {
      return {
        status: 'invalid',
        mode: 'file' as const,
        connectorId,
        approvedHosts: metadata.filter((result) => result.success).map((result) => result.data),
        message: 'Approved hosts must be exact hostnames.',
        retryable: false
      };
    }
    let document: Record<string, unknown>;
    try { document = await readCatalogFile(file); } catch { return { status: 'invalid', mode: 'file', connectorId, approvedHosts, message: 'The JSON file must contain a valid JSON object.', retryable: false }; }
    try {
      await api.openApiConnectors.imports.importJson(connectorId, { document, approved_hosts: approvedHosts });
    } catch (error) {
      return safeImportError(error, 'file', connectorId, { approvedHosts });
    }
    return operationRedirect(listLocation(connectorId, { imported: 'true' }));
  },
  importDocument: async (api, data) => {
    const connectorId = connectorIdFromForm(data);
    const approvedHosts = parseApprovedHosts(data);
    const url = String(data.get('url') ?? '').trim();
    const documentRaw = String(data.get('document') ?? '');
    let document: unknown;
    if (!connectorId) {
      return {
        status: 'invalid',
        mode: 'url' as const,
        url,
        approvedHosts,
        message: 'Choose a connector to import into.',
        retryable: false
      };
    }
    try {
      document = JSON.parse(documentRaw);
    } catch {
      return {
        status: 'invalid',
        mode: 'url' as const,
        connectorId,
        url,
        approvedHosts,
        message: 'The retrieved OpenAPI document is not valid JSON.',
        retryable: false
      };
    }
    const parsed = importOpenApiCatalogDocumentRequestSchema.safeParse({ document, approved_hosts: approvedHosts });
    if (!parsed.success) {
      return {
        status: 'invalid',
        mode: 'url' as const,
        connectorId,
        url,
        approvedHosts,
        message:
          approvedHosts.length === 0
            ? 'Add at least one exact hostname.'
            : 'The retrieved OpenAPI document or approved hostnames are not valid.',
        retryable: false
      };
    }
    try {
      await api.openApiConnectors.imports.importJson(connectorId, parsed.data);
    } catch (error) {
      return safeImportError(error, 'url', connectorId, { url, approvedHosts });
    }
    return operationRedirect(listLocation(connectorId, { imported: 'true' }));
  },
  saveToolActivations: async (api, data) => {
    const connectorId = connectorIdFromForm(data);
    let candidate: unknown;
    try {
      candidate = JSON.parse(String(data.get('toolActivations') ?? ''));
    } catch {
      return operationFailure(422, { status: 'invalid', message: 'Tool activation changes are invalid.' });
    }
    const activationTools = typeof candidate === 'object' && candidate !== null && 'tools' in candidate && Array.isArray(candidate.tools) ? candidate.tools : [];
    const parsed = activationTools.length ? openApiToolActivationBatchRequestSchema.safeParse(candidate) : null;
    let policyCandidate: unknown;
    try { policyCandidate = JSON.parse(String(data.get('invocationPolicies') ?? '')); } catch { return operationFailure(422, { status: 'invalid', message: 'Invocation policy changes are invalid.' }); }
    const policyTools = typeof policyCandidate === 'object' && policyCandidate !== null && 'tools' in policyCandidate && Array.isArray(policyCandidate.tools) ? policyCandidate.tools : [];
    const policies = policyTools.length ? invocationPolicyBatchUpdateRequestSchema.safeParse(policyCandidate) : null;
    if (!connectorId || (parsed && !parsed.success) || (policies && !policies.success) || (!parsed && !policies)) return operationFailure(422, { status: 'invalid', message: 'Tool changes are invalid.' });
    try {
      const changes = new Map<string, { toolId: string; activationStatus?: 'enabled' | 'disabled'; invocationMode?: 'direct' | 'ask'; expectedPolicyRevision?: number }>();
      parsed?.data.tools.forEach((tool) => changes.set(tool.tool_id, { toolId: tool.tool_id, activationStatus: tool.activation_status }));
      policies?.data.tools.forEach((tool) => changes.set(tool.tool_id, { ...changes.get(tool.tool_id), toolId: tool.tool_id, invocationMode: tool.mode, expectedPolicyRevision: tool.expected_revision }));
      const response = await api.openApiConnectors.connectors.saveActivations(connectorId, [...changes.values()]);
      const activationToolIds = new Set(parsed?.data.tools.map((tool) => tool.tool_id) ?? []);
      const policyToolIds = new Set(policies?.data.tools.map((tool) => tool.tool_id) ?? []);
      const activationResponse = { ...response, tools: response.tools.filter((tool) => activationToolIds.has(tool.tool_id)) };
      const policyResponse = { connector_kind: 'openapi' as const, connector_id: connectorId, tools: response.tools.filter((tool) => policyToolIds.has(tool.tool_id)).map((tool) => ({ tool_id: tool.tool_id, mode: tool.invocation_mode, revision: tool.policy_revision })) };
      return { activationResponse, policyResponse };
    } catch (error) {
      const conflict = error instanceof HttpError && error.status === 409 ? invocationPolicyConflictResponseSchema.safeParse(error.body) : undefined;
      if (!conflict?.success && !isOperationalError(error)) throw error;
      const original = conflict?.success
        ? { status: 409, data: { status: 'conflict' as const, connectorId, message: 'Invocation policies changed by another administrator.', policyConflicts: conflict.data.conflicts } }
        : { status: 503, data: { status: 'failed' as const, connectorId, message: 'Tool activation changes could not be saved. Try again.' } };
      const presented = await presentSaveFailureWithReconciliation({
        originalError: error,
        presentOriginal: () => original,
        loadAuthoritative: () => api.openApiConnectors.connectors.listActivations(connectorId),
        presentAuthoritative: (authoritativeActivationResponse) => ({
          authoritativeActivationResponse,
          authoritativePolicyResponse: { connector_kind: 'openapi' as const, connector_id: connectorId, tools: authoritativeActivationResponse.tools.map((tool) => ({ tool_id: tool.tool_id, mode: tool.invocation_mode, revision: tool.policy_revision })) }
        })
      });
      return operationFailure(presented.status, presented.data);
    }
  },
  publish: async (api, data) => {
    const connectorId = connectorIdFromForm(data);
    if (!connectorId) return { status: 'invalid', message: 'Choose a connector to publish.' };
    const result = await setOpenApiPublication(api.openApiConnectors, connectorId, 'published');
    if (result.status === 'saved') return operationRedirect(listLocation(connectorId, { published: 'true' }));
    return { ...result, connectorId };
  },
  unpublish: async (api, data) => {
    const connectorId = connectorIdFromForm(data);
    if (!connectorId) return { status: 'invalid', message: 'Choose a connector to unpublish.' };
    const result = await setOpenApiPublication(api.openApiConnectors, connectorId, 'unpublished');
    if (result.status === 'saved') return operationRedirect(listLocation(connectorId, { unpublished: 'true' }));
    return { ...result, connectorId };
  }
};
