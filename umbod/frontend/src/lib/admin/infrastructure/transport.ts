import { env } from '$env/dynamic/private';
import { z } from 'zod';

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export type TransportRequestBody =
  | { kind: 'absent' }
  | { kind: 'json'; value: unknown; schema: z.ZodType<unknown> }
  | { kind: 'multipart'; form: FormData; metadata: unknown; metadataSchema: z.ZodType<unknown> };

export interface TransportRequest<TOut> {
  method: HttpMethod;
  path: string;
  outputSchema?: z.ZodType<TOut>;
  requestBody?: TransportRequestBody;
  body?: unknown;
  inputSchema?: z.ZodType<unknown>;
}

export interface Transport {
  request<TOut>(opts: TransportRequest<TOut>): Promise<TOut>;
}

export class SchemaValidationError extends Error {
  constructor(
    readonly direction: 'outbound' | 'inbound',
    readonly issues: z.core.$ZodIssue[]
  ) {
    super(`Schema validation failed (${direction}): ${z.prettifyError({ issues } as z.ZodError)}`);
    this.name = 'SchemaValidationError';
  }
}

export class HttpError extends Error {
  constructor(
    readonly status: number,
    readonly statusText: string,
    readonly body: unknown
  ) {
    super(`HTTP ${status}: ${statusText}`);
    this.name = 'HttpError';
  }
}

export class NetworkError extends Error {
  constructor(readonly cause: unknown) {
    super('The service could not be reached');
    this.name = 'NetworkError';
  }
}

export function isOperationalError(error: unknown): error is HttpError | NetworkError {
  return error instanceof HttpError || error instanceof NetworkError;
}

interface TransportConfig {
  fetch: typeof globalThis.fetch;
  baseUrl: string;
  authHeaders: HeadersInit;
}

const defaultPrivateApiBaseUrl = 'http://api:8000';
const defaultPrivateAuthTokenHeader = 'authorization';
const proxyAccessTokenHeaders = ['authorization', 'x-auth-request-access-token', 'x-forwarded-access-token'];

class HttpTransport implements Transport {
  constructor(private readonly config: TransportConfig) {}

  async request<TOut>(opts: TransportRequest<TOut>): Promise<TOut> {
    const init = this.buildRequestInit(opts);
    let response: Response;
    try {
      response = await this.config.fetch(`${this.config.baseUrl}${opts.path}`, init);
    } catch (error) {
      throw new NetworkError(error);
    }

    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new HttpError(response.status, response.statusText, body);
    }

    if (opts.outputSchema === undefined) {
      return undefined as TOut;
    }

    const payload = await response.json();
    const parsed = opts.outputSchema.safeParse(payload);
    if (!parsed.success) {
      throw new SchemaValidationError('inbound', parsed.error.issues);
    }

    return parsed.data;
  }

  private buildRequestInit(opts: TransportRequest<unknown>): RequestInit {
    const requestBody = opts.requestBody ?? this.legacyRequestBody(opts) ?? { kind: 'absent' };
    if (requestBody.kind === 'absent') {
      return { method: opts.method, ...this.authRequestHeaders() };
    }
    if (requestBody.kind === 'multipart') {
      this.parseOutbound(requestBody.metadataSchema, requestBody.metadata);
      return { method: opts.method, ...this.authRequestHeaders(), body: requestBody.form };
    }
    const parsed = this.parseOutbound(requestBody.schema, requestBody.value);
    return {
      method: opts.method,
      headers: { ...this.config.authHeaders, 'content-type': 'application/json' },
      body: JSON.stringify(parsed)
    };
  }

  private legacyRequestBody(opts: TransportRequest<unknown>): TransportRequestBody | undefined {
    if (opts.body === undefined) return undefined;
    if (opts.inputSchema === undefined) throw new Error(`Missing inputSchema for ${opts.method} ${opts.path}`);
    return { kind: 'json', value: opts.body, schema: opts.inputSchema };
  }

  private parseOutbound(schema: z.ZodType<unknown>, value: unknown): unknown {
    const parsed = schema.safeParse(value);
    if (!parsed.success) throw new SchemaValidationError('outbound', parsed.error.issues);
    return parsed.data;
  }

  private authRequestHeaders(): Pick<RequestInit, 'headers'> | Record<string, never> {
    return Object.keys(this.config.authHeaders).length === 0 ? {} : { headers: this.config.authHeaders };
  }
}

export function privateApiBaseUrl(): string {
  return env.PRIVATE_API_BASE_URL ?? defaultPrivateApiBaseUrl;
}

export function serverTransport(fetch: typeof globalThis.fetch, request?: Request): Transport {
  return new HttpTransport({ fetch, baseUrl: privateApiBaseUrl(), authHeaders: forwardedAuthHeaders(request) });
}

export function forwardedAuthHeaders(request?: Request): HeadersInit {
  if (request === undefined) {
    return {};
  }
  const headerName = privateAuthTokenHeader();
  const token = [headerName, ...proxyAccessTokenHeaders]
    .map((candidateHeader) => request.headers.get(candidateHeader))
    .find((candidateToken) => candidateToken !== null);
  if (token === undefined || token === null) {
    return {};
  }
  return { [headerName]: token };
}

function privateAuthTokenHeader(): string {
  return env.PRIVATE_AUTH_TOKEN_HEADER ?? defaultPrivateAuthTokenHeader;
}
