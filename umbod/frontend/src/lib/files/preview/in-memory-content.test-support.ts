import type { FileContentPort } from './ports';

export class InMemoryFileContent implements FileContentPort {
  readonly requests: { id: string; signal: AbortSignal }[] = [];

  constructor(private readonly load: (id: string, signal: AbortSignal) => Promise<string | Uint8Array>) {}

  async readText(id: string, signal: AbortSignal): Promise<string> {
    this.requests.push({ id, signal });
    const content = await this.load(id, signal);
    return typeof content === 'string' ? content : new TextDecoder('utf-8', { fatal: true }).decode(content);
  }

  async readBytes(id: string, signal: AbortSignal): Promise<Uint8Array> {
    this.requests.push({ id, signal });
    const content = await this.load(id, signal);
    return typeof content === 'string' ? new TextEncoder().encode(content) : content;
  }
}
