import { publicConfigurationProvider, type PublicConfigurationProvider } from './public-configuration';
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
  signal?: AbortSignal;
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
  signIn?: () => void;
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
    const request = this.config.fetch ?? globalThis.fetch;
    let response: Response;
    try {
      response = await request(`${configuration.apiBaseUrl.replace(/\/$/, '')}${opts.path}`, { ...init, signal: opts.signal, credentials: 'same-origin' });
    } catch (error) {
      if (opts.signal?.aborted) throw error;
      throw new NetworkError(error);
    }

    if (response.status === 401) {
      try { (this.config.signIn ?? navigateToSignIn)(); } finally { throw new AuthenticationRequiredError(); }
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
      headers: { ...this.authRequestHeaders().headers, 'content-type': 'application/json' },
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

  private authRequestHeaders(): { headers: Record<string, string> } {
    const token = this.config.bearerToken?.();
    return { headers: { 'X-Umbod-Web-Request': '1', ...(token ? { authorization: `Bearer ${token}` } : {}) } };
  }
}

export function browserTransport(config: BrowserTransportConfig = {}): Transport {
  return new HttpTransport(config);
}
