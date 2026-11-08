import {
  CodexPluginArchiveSchema,
  type CodexPluginArchive,
  type CodexPluginDownloader,
  type CodexPluginPackager,
  type CodexPluginRequest
} from './contracts';

export function testArchive(endpoint: string): CodexPluginArchive {
  return CodexPluginArchiveSchema.parse({
    endpoint,
    marketplaceName: 'umbod-0123456789ab',
    filename: 'umbod-codex-0123456789ab.zip',
    bytes: new Uint8Array([80, 75])
  });
}

export class InMemoryCodexPluginPackager implements CodexPluginPackager {
  requests: CodexPluginRequest[] = [];
  failure: Error | null = null;
  result: Promise<CodexPluginArchive> | null = null;

  async prepare(request: CodexPluginRequest): Promise<CodexPluginArchive> {
    this.requests.push(request);
    if (this.failure) throw this.failure;
    return this.result ?? testArchive(request.endpoint);
  }
}

export class InMemoryCodexPluginDownloader implements CodexPluginDownloader {
  downloads: CodexPluginArchive[] = [];
  failure: Error | null = null;

  save(archive: CodexPluginArchive): void {
    if (this.failure) throw this.failure;
    this.downloads.push(archive);
  }
}
