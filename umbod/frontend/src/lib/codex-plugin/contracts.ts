import { z } from 'zod';

export function normalizePluginEndpoint(value: string): string {
  if (!value || /[\s\u0000-\u001f\u007f\\${}]/u.test(value) || !/^https?:\/\//i.test(value)) {
    throw new Error('Use a literal HTTP or HTTPS MCP endpoint without whitespace or placeholders.');
  }
  const authority = /^https?:\/\/([^/?#]+)/i.exec(value)?.[1];
  if (!authority) throw new Error('The MCP endpoint requires a host.');
  const parsed = new URL(value);
  if (authority.includes('@') || parsed.username || parsed.password || value.includes('?') || value.includes('#')) {
    throw new Error('The MCP endpoint must not contain credentials, a query, or a fragment.');
  }
  const hostname = authority.startsWith('[') ? authority.slice(0, authority.indexOf(']') + 1) : authority.split(':')[0];
  const loopback = hostname.toLowerCase() === 'localhost' ||
    (hostname.startsWith('[') && parsed.hostname === '[::1]') ||
    /^127\.(?:0|[1-9]\d{0,2})\.(?:0|[1-9]\d{0,2})\.(?:0|[1-9]\d{0,2})$/.test(hostname);
  if (parsed.protocol === 'http:' && !loopback) {
    throw new Error('Remote MCP endpoints require HTTPS.');
  }
  const base = value.replace(/^[^:]+:/, parsed.protocol).replace(/\/+$/, '');
  return base.endsWith('/mcp') ? base : `${base}/mcp`;
}

export const CodexPluginRequestSchema = z.object({
  endpoint: z.string().transform((value, context): string => {
    try {
      return normalizePluginEndpoint(value);
    } catch {
      context.addIssue({ code: 'custom', message: 'Use an HTTPS MCP URL, or HTTP on loopback, without credentials, query parameters, or a fragment.' });
      return z.NEVER;
    }
  })
});

export type CodexPluginRequest = z.infer<typeof CodexPluginRequestSchema>;

export const CodexPluginReceiptSchema = z.object({
  endpoint: z.string(),
  marketplaceName: z.string().regex(/^umbod-[a-f0-9]{12}$/),
  filename: z.string().regex(/^umbod-codex-[a-f0-9]{12}\.zip$/)
});

export type CodexPluginReceipt = z.infer<typeof CodexPluginReceiptSchema>;

export const CodexPluginArchiveSchema = CodexPluginReceiptSchema.extend({
  bytes: z.instanceof(Uint8Array)
});

export type CodexPluginArchive = z.infer<typeof CodexPluginArchiveSchema>;

export interface CodexPluginPackager {
  prepare(request: CodexPluginRequest): Promise<CodexPluginArchive>;
}

export interface CodexPluginDownloader {
  save(archive: CodexPluginArchive): void;
}
