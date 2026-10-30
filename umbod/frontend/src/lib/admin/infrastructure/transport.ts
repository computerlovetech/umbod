import { publicConfigurationProvider, type PublicConfigurationProvider } from './public-configuration';
import { z } from 'zod';

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'OPTIONS';

export type TransportRequestBody =
  | { kind: 'absent' }
  | { kind: 'json'; value: unknown; schema: z.ZodType<unknown> }
  | { kind: 'raw'; value: File; schema: z.ZodType<File>; headers: Record<string, string> }
  | { kind: 'multipart'; form: FormData; metadata: unknown; metadataSchema: z.ZodType<unknown> };

const conditionalHeadersSchema = z.strictObject({ 'If-Match': z.string().regex(/^"[\x21\x23-\x2b\x2d-\x7e]+"$/) });

export interface TransportRequest<TOut> {
  method: HttpMethod;
  path: string;
  outputSchema?: z.ZodType<TOut>;
  requestBody?: TransportRequestBody;
  body?: unknown;
  inputSchema?: z.ZodType<unknown>;
  signal?: AbortSignal;
  redirect?: 'error';
  responseBody?: 'headers';
  conditionalHeaders?: z.infer<typeof conditionalHeadersSchema>;
  apiEndpoint?: { method: HttpMethod; path: string };
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

export interface BrowserTransportConfig {
  fetch?: typeof globalThis.fetch;
  configuration?: PublicConfigurationProvider;
  bearerToken?: () => string | undefined;
  origin?: () => string;
}

export class AuthenticationRequiredError extends Error {
  constructor() { super('Authentication is required'); this.name = 'AuthenticationRequiredError'; }
}

export function navigateToSignIn(): void {
  const returnPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  window.location.assign(`/oauth2/sign_in?rd=${encodeURIComponent(returnPath)}`);
}

class HttpTransport implements Transport {
  constructor(private readonly config: BrowserTransportConfig) {}

  async request<TOut>(opts: TransportRequest<TOut>): Promise<TOut> {
    const init = this.buildRequestInit(opts);
    const configuration = await (this.config.configuration ?? publicConfigurationProvider).get();
    const url = this.requestUrl(opts, configuration.apiBaseUrl);
    const request = this.config.fetch ?? globalThis.fetch;
    let response: Response;
    try {
      response = await request(url, { ...init, signal: opts.signal, credentials: 'same-origin', redirect: opts.apiEndpoint ? 'error' : opts.redirect });
    } catch (error) {
      if (opts.signal?.aborted) throw error;
      throw new NetworkError(error);
    }

    if (response.status === 401) {
      throw new AuthenticationRequiredError();
    }

    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new HttpError(response.status, response.statusText, body);
    }

    if (opts.outputSchema === undefined) {
      return undefined as TOut;
    }

    const payload = opts.responseBody === 'headers' ? { allow: response.headers.get('Allow') } : await response.json();
    const parsed = opts.outputSchema.safeParse(payload);
    if (!parsed.success) {
      throw new SchemaValidationError('inbound', parsed.error.issues);
    }

    return parsed.data;
  }

  private requestUrl(opts: TransportRequest<unknown>, base: string): string {
    if (opts.apiEndpoint === undefined) return `${base.replace(/\/$/, '')}${opts.path}`;
    const relativeBase = base.startsWith('/');
    const api = relativeBase ? new URL(base, this.config.origin?.() ?? window.location.origin) : new URL(base);
    const expected = `${api.pathname.replace(/\/$/, '')}${opts.apiEndpoint.path}`;
    const url = new URL(opts.path, api.origin);
    if (opts.method !== opts.apiEndpoint.method || url.origin !== api.origin || url.pathname !== expected || url.username || url.password || url.search || url.hash) throw new Error('Unsafe API endpoint');
    return relativeBase ? url.pathname : url.href;
  }

  private buildRequestInit(opts: TransportRequest<unknown>): RequestInit {
    const requestBody = opts.requestBody ?? this.legacyRequestBody(opts) ?? { kind: 'absent' };
    const conditional = opts.conditionalHeaders ? this.parseOutbound(conditionalHeadersSchema, opts.conditionalHeaders) : {};
    if (requestBody.kind === 'absent') {
      return { method: opts.method, headers: { ...this.authRequestHeaders().headers, ...conditional } };
    }
    if (requestBody.kind === 'raw') {
      const body = this.parseOutbound(requestBody.schema, requestBody.value);
      return { method: opts.method, headers: { ...this.authRequestHeaders().headers, ...requestBody.headers, ...conditional }, body };
    }
    if (requestBody.kind === 'multipart') {
      this.parseOutbound(requestBody.metadataSchema, requestBody.metadata);
      return { method: opts.method, headers: { ...this.authRequestHeaders().headers, ...conditional }, body: requestBody.form };
    }
    const parsed = this.parseOutbound(requestBody.schema, requestBody.value);
    return {
      method: opts.method,
      headers: { ...this.authRequestHeaders().headers, 'content-type': 'application/json', ...conditional },
      body: JSON.stringify(parsed)
    };
  }

  private legacyRequestBody(opts: TransportRequest<unknown>): TransportRequestBody | undefined {
    if (opts.body === undefined) return undefined;
    if (opts.inputSchema === undefined) throw new Error(`Missing inputSchema for ${opts.method} ${opts.path}`);
    return { kind: 'json', value: opts.body, schema: opts.inputSchema };
  }

  private parseOutbound<T>(schema: z.ZodType<T>, value: unknown): T {
    const parsed = schema.safeParse(value);
    if (!parsed.success) throw new SchemaValidationError('outbound', parsed.error.issues);
    return parsed.data;
  }

  private authRequestHeaders(): { headers: Record<string, string> } {
    const token = this.config.bearerToken?.();
    return { headers: { 'X-Umbod-Web-Request': '1', ...(token ? { authorization: `Bearer ${token}` } : {}) } };
  }
}

export function browserTransport(config: BrowserTransportConfig = {}): Transport {
  return new HttpTransport(config);
}
