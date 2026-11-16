import { z } from 'zod';
import { endpointSchema, issuerSchema, scopesSchema } from './schemas';

export const discoveryEndpointSchema = endpointSchema.and(issuerSchema);

export const endpointDiscoveryRequestSchema = z.object({
  endpoint_url: discoveryEndpointSchema,
  issuer_selection: z.discriminatedUnion('kind', [
    z.object({ kind: z.literal('automatic') }).strict(),
    z.object({ kind: z.literal('selected'), issuer_url: issuerSchema }).strict()
  ])
}).strict();

export const endpointDiscoveryResultSchema = z.discriminatedUnion('kind', [
  z.object({
    kind: z.literal('issuer_selection_required'),
    endpoint_url: discoveryEndpointSchema,
    issuer_urls: z.array(issuerSchema).min(2).max(16).refine((issuers): boolean => new Set(issuers).size === issuers.length)
  }).strict(),
  z.object({
    kind: z.literal('discovered'),
    endpoint_url: discoveryEndpointSchema,
    issuer_url: issuerSchema,
    available_scopes: scopesSchema,
    scope_source: z.enum(['resource', 'authorization_server', 'unavailable']),
    automatic_registration: z.enum(['available', 'unavailable']),
    token_endpoint_auth_methods: z.array(z.string().min(1).max(128)).max(16)
  }).strict()
]);

export type EndpointDiscoveryRequest = z.infer<typeof endpointDiscoveryRequestSchema>;
export type EndpointDiscoveryResult = z.infer<typeof endpointDiscoveryResultSchema>;

export function endpointDiscoveryResultForRequest(request: EndpointDiscoveryRequest): z.ZodType<EndpointDiscoveryResult> {
  return endpointDiscoveryResultSchema.refine((result): boolean =>
    result.endpoint_url === request.endpoint_url &&
    (request.issuer_selection.kind === 'automatic' ||
      (result.kind === 'discovered' && result.issuer_url === request.issuer_selection.issuer_url))
  );
}
