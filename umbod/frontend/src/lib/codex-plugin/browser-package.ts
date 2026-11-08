import { strToU8, zipSync } from 'fflate';
import { z } from 'zod';
import templateData from './package-template.json';
import {
  CodexPluginArchiveSchema,
  CodexPluginRequestSchema,
  type CodexPluginArchive,
  type CodexPluginDownloader,
  type CodexPluginPackager,
  type CodexPluginRequest
} from './contracts';

const template = z.object({
  endpointPlaceholder: z.string().min(1),
  marketplacePlaceholder: z.string().min(1),
  files: z.record(z.string(), z.string())
}).parse(templateData);

export function renderPackageFiles(request: CodexPluginRequest, marketplaceName: string): Record<string, string> {
  return Object.fromEntries(Object.entries(template.files).map(([path, content]): [string, string] => [
    path,
    content
      .replaceAll(JSON.stringify(template.endpointPlaceholder), JSON.stringify(request.endpoint))
      .replaceAll(JSON.stringify(template.marketplacePlaceholder), JSON.stringify(marketplaceName))
  ]));
}

export class BrowserCodexPluginPackager implements CodexPluginPackager {
  async prepare(request: CodexPluginRequest): Promise<CodexPluginArchive> {
    const selected = CodexPluginRequestSchema.parse(request);
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(selected.endpoint));
    const identity = Array.from(new Uint8Array(digest), (byte): string => byte.toString(16).padStart(2, '0')).join('').slice(0, 12);
    const marketplaceName = `umbod-${identity}`;
    const files = renderPackageFiles(selected, marketplaceName);
    const entries = Object.fromEntries(Object.entries(files).map(([path, content]): [string, Uint8Array] => [path, strToU8(content)]));
    return CodexPluginArchiveSchema.parse({
      endpoint: selected.endpoint,
      marketplaceName,
      filename: `umbod-codex-${identity}.zip`,
      bytes: zipSync(entries, { level: 6 })
    });
  }
}

export class BrowserCodexPluginDownloader implements CodexPluginDownloader {
  save(archive: CodexPluginArchive): void {
    const selected = CodexPluginArchiveSchema.parse(archive);
    const url = URL.createObjectURL(new Blob([new Uint8Array(selected.bytes).buffer], { type: 'application/zip' }));
    const link = document.createElement('a');
    try {
      link.href = url;
      link.download = selected.filename;
      document.body.append(link);
      link.click();
    } finally {
      link.remove();
      setTimeout((): void => URL.revokeObjectURL(url), 1000);
    }
  }
}
