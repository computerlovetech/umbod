import { z } from 'zod';
import { approvedHostnameSchema, createOpenApiConnectorRequestSchema } from './openapi-connectors';

export const openApiSetupRequestSchema = createOpenApiConnectorRequestSchema.extend({
  document: z.record(z.string(), z.unknown()),
  approved_hosts: z.array(approvedHostnameSchema).min(1),
  authentication_type: z.enum(['none', 'bearer']),
  bearer_token: z.string()
}).refine((value) => value.authentication_type !== 'bearer' || value.bearer_token.trim().length > 0, 'Enter a bearer token');
export type OpenApiSetupRequest = z.infer<typeof openApiSetupRequestSchema>;
const cleanupFailureSchema = z.object({ code: z.literal('openapi_setup_cleanup_failed'), connector_id: z.string().min(1) });
export const openApiSetupCleanupFailureSchema = z.object({ detail: cleanupFailureSchema }).transform((value) => value.detail);
