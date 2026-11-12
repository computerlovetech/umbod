import { z } from 'zod';
import { ResponseTooLargeError, type Transport } from '$lib/admin/infrastructure/transport';
import { nodeIdSchema } from '../domain/schemas';
import { PreviewReadError, type FileContentPort } from '../preview/ports';
import { readFailure } from '../errors';

export const previewByteLimit = 1024 * 1024;
const previewTextSchema = z.string();

export class FileContentRoute implements FileContentPort {
  constructor(private readonly transport: Transport) {}

  readText(id: string, signal: AbortSignal): Promise<string> {
    return this.read(id, signal, 'text', previewTextSchema);
  }

  readBytes(id: string, signal: AbortSignal): Promise<Uint8Array> {
    return this.read(id, signal, 'bytes', z.instanceof(Uint8Array));
  }

  private async read<T>(id: string, signal: AbortSignal, kind: 'text' | 'bytes', outputSchema: z.ZodType<T>): Promise<T> {
    const nodeId = nodeIdSchema.parse(id);
    try {
      return await this.transport.request({
        method: 'GET',
        path: '/me/filesystem/nodes/' + encodeURIComponent(nodeId) + '/content?delivery=stream',
        outputSchema,
        responseBody: { kind, maxBytes: previewByteLimit },
        redirect: 'error',
        signal
      });
    } catch (error) {
      if (signal.aborted) throw error;
      const failure = readFailure(error);
      throw new PreviewReadError(error instanceof ResponseTooLargeError ? 'too-large' : failure === 'denied' || failure === 'sign-in' || failure === 'missing' ? failure : 'error');
    }
  }
}
