import { env } from '$env/dynamic/public';
import { z } from 'zod';

const runtimeConfigurationSchema = z.object({
  publicMcpBaseUrl: z.url()
});

export type RuntimeConfiguration = z.infer<typeof runtimeConfigurationSchema>;

export interface RuntimeConfigurationProvider {
  get(): RuntimeConfiguration;
}

const defaultRuntimeConfiguration: RuntimeConfiguration = {
  publicMcpBaseUrl: 'http://localhost:8011'
};

export class InMemoryRuntimeConfigurationProvider implements RuntimeConfigurationProvider {
  constructor(private readonly configuration: RuntimeConfiguration = defaultRuntimeConfiguration) {}

  get(): RuntimeConfiguration {
    return runtimeConfigurationSchema.parse(this.configuration);
  }
}

export class EnvironmentRuntimeConfigurationProvider implements RuntimeConfigurationProvider {
  constructor(private readonly values: Record<string, string | undefined>) {}

  get(): RuntimeConfiguration {
    return runtimeConfigurationSchema.parse({
      publicMcpBaseUrl: this.values.PUBLIC_MCP_BASE_URL ?? defaultRuntimeConfiguration.publicMcpBaseUrl
    });
  }
}

export function runtimeConfigurationProvider(): RuntimeConfigurationProvider {
  return new EnvironmentRuntimeConfigurationProvider(env);
}
