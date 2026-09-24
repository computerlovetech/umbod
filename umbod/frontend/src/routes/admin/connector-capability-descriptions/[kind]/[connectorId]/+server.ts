import { json, type RequestHandler } from '@sveltejs/kit';
import { connectorKindSchema, clearCapabilityDescriptionRequestSchema, setCapabilityDescriptionRequestSchema } from '$lib/admin/capability-descriptions';
import { CapabilityDescriptionConflictError } from '$lib/admin/capability-descriptions-api';
import { adminServerApi } from '$lib/admin/infrastructure/server-api';
import { HttpError } from '$lib/admin/infrastructure/transport';

function routeParams(params: Partial<Record<string, string>>) {
  return { kind: connectorKindSchema.parse(params.kind), connectorId: String(params.connectorId ?? '') };
}
export const GET: RequestHandler = async (event) => {
  const params = routeParams(event.params);
  return json(await adminServerApi(event).capabilityDescriptions.get(params.kind, params.connectorId));
};
export const PUT: RequestHandler = async (event) => {
  const api = adminServerApi(event).capabilityDescriptions;
  const params = routeParams(event.params);
  const payload: unknown = await event.request.json();
  try {
    if (typeof payload === 'object' && payload !== null && 'action' in payload && payload.action === 'set') {
      const request = setCapabilityDescriptionRequestSchema.parse(payload);
      return json(await api.set(params.kind, params.connectorId, request.description, request.expected_revision));
    }
    const request = clearCapabilityDescriptionRequestSchema.parse(payload);
    return json(await api.clear(params.kind, params.connectorId, request.expected_revision));
  } catch (error) {
    if (error instanceof CapabilityDescriptionConflictError) return json({ detail: { code: 'capability_description_revision_conflict', current: error.current } }, { status: 409 });
    if (error instanceof HttpError) return json(error.body, { status: error.status });
    throw error;
  }
};
