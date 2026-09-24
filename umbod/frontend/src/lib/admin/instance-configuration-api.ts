import type { Transport } from "./infrastructure/transport";
import {
  instanceConfigurationSchema,
  type InstanceConfiguration,
} from "./instance-configuration";

export interface InstanceConfigurationRoute {
  get(): Promise<InstanceConfiguration>;
}

export class HttpInstanceConfigurationRoute implements InstanceConfigurationRoute {
  constructor(private readonly transport: Transport) {}

  get(): Promise<InstanceConfiguration> {
    return this.transport.request({
      method: "GET",
      path: "/admin/instance-configuration",
      outputSchema: instanceConfigurationSchema,
    });
  }
}
