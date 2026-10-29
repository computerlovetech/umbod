import { HttpError, NetworkError, SchemaValidationError, type Transport } from '$lib/admin/infrastructure/transport';
import type { UploadTransferPort } from '../api';
import { nodeIdSchema, rawUploadSchema, uploadTransferSchema, type UploadTransfer } from '../domain/schemas';

export type OriginProvider = () => string;

export function browserOrigin(): string {
  return window.location.origin;
}

export class HttpUploadTransfer implements UploadTransferPort {
  constructor(private readonly transport: Transport, private readonly origin: OriginProvider = browserOrigin, private readonly fetch: typeof globalThis.fetch = globalThis.fetch) {}

  transfer = async (descriptor: UploadTransfer, file: File, sessionId: string): Promise<void> => {
    const parsed = uploadTransferSchema.safeParse(descriptor);
    if (!parsed.success) throw new SchemaValidationError('inbound', parsed.error.issues);
    const body = rawUploadSchema.safeParse(file);
    if (!body.success) throw new SchemaValidationError('outbound', body.error.issues);
    const transfer = parsed.data;
    if (transfer.authorization.type === 'same_origin') {
      const protectedHeader = Object.keys(transfer.headers).some((name) => /^(authorization|proxy-.*|cookie|cookie2|set-cookie|host|origin|referer|csrf-token|xsrf-token|x-umbod-.*|x-csrf.*|x-xsrf.*|x-forwarded-.*|sec-.*)$/i.test(name));
      if (protectedHeader) throw new Error('Upload instructions cannot override application credentials');
      await this.transport.request({ method: transfer.method, path: transfer.url, apiEndpoint: { method: 'PUT', path: `/me/filesystem/uploads/${nodeIdSchema.parse(sessionId)}/content` }, redirect: 'error', requestBody: { kind: 'raw', value: body.data, schema: rawUploadSchema, headers: transfer.headers } });
      return;
    }
    const url = new URL(transfer.url, this.origin());
    if (url.username || url.password || url.hash) throw new Error('Unsafe upload transfer URL');
    if (url.protocol !== 'https:') throw new Error('External upload requires HTTPS');
    let response: Response;
    try {
      response = await this.fetch(url.href, { method: transfer.method, body: body.data, headers: transfer.headers, credentials: 'omit', redirect: 'error', referrerPolicy: 'no-referrer' });
    } catch (error) {
      throw new NetworkError(error);
    }
    if (!response.ok) throw new HttpError(response.status, response.statusText, {});
  };
}
