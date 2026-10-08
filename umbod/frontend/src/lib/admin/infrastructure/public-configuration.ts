import { dev } from '$app/environment';
import { z } from 'zod';

const publicBaseSchema = z.string().refine((value) => {
  if (value.startsWith('/') && !value.startsWith('//')) return !value.includes('?') && !value.includes('#');
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password && !url.search && !url.hash;
  } catch { return false; }
}, 'Expected a same-origin path or HTTP URL');

export const logoutConfigurationSchema = z.object({
  auth0Domain: z.string().max(253).regex(/^(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$/),
  clientId: z.string().min(1).max(256).regex(/^[^\s\x00-\x1f\x7f]+$/),
  returnTo: z.string().regex(/^https:\/\/[^\s/?#@]+\/signed-out\.html$/).refine((value) => {
    try {
      const url = new URL(value);
      return url.protocol === 'https:' && !url.username && !url.password && !url.search && !url.hash && url.pathname === '/signed-out.html' && !/[\s\\\x00-\x1f\x7f]/.test(value);
    } catch { return false; }
  }, 'Expected the fixed HTTPS signed-out page')
}).strict();
export type LogoutConfiguration = z.infer<typeof logoutConfigurationSchema>;

export const publicConfigurationSchema = z.object({
  apiBaseUrl: publicBaseSchema,
  mcpBaseUrl: publicBaseSchema,
  logout: logoutConfigurationSchema.nullable().optional()
});
export type PublicConfiguration = z.infer<typeof publicConfigurationSchema>;

export interface PublicConfigurationProvider {
  get(): Promise<PublicConfiguration>;
}

export class InMemoryPublicConfigurationProvider implements PublicConfigurationProvider {
  constructor(private readonly configuration: PublicConfiguration) {}
  async get(): Promise<PublicConfiguration> { return publicConfigurationSchema.parse(this.configuration); }
}

export class BrowserPublicConfigurationProvider implements PublicConfigurationProvider {
  private pending: Promise<PublicConfiguration> | undefined;
  constructor(private readonly request: typeof fetch) {}
  get(): Promise<PublicConfiguration> {
    this.pending ??= this.load().catch((cause: unknown) => { this.pending = undefined; throw cause; });
    return this.pending;
  }
  private async load(): Promise<PublicConfiguration> {
    const response = await this.request('/app-config.json', { credentials: 'same-origin', cache: 'no-store' });
    if (response.status === 404 && dev) return { apiBaseUrl: '/api', mcpBaseUrl: 'http://localhost:8011' };
    if (!response.ok) throw new Error('Public application configuration could not be loaded');
    return publicConfigurationSchema.parse(await response.json());
  }
}

export const publicConfigurationProvider: PublicConfigurationProvider = new BrowserPublicConfigurationProvider((input, init) => globalThis.fetch(input, init));
