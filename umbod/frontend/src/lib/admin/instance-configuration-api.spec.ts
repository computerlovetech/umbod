import { describe, expect, test } from "vitest";
import { HttpInstanceConfigurationRoute } from "./instance-configuration-api";
import type { Transport, TransportRequest } from "./infrastructure/transport";

class RecordingTransport implements Transport {
  requestOptions: TransportRequest<unknown> | undefined;

  async request<TOut>(options: TransportRequest<TOut>): Promise<TOut> {
    this.requestOptions = options;
    return options.outputSchema?.parse({ groups: [] }) as TOut;
  }
}

describe("instance configuration route", () => {
  test("gets the authenticated admin instance configuration resource", async () => {
    const transport = new RecordingTransport();
    const route = new HttpInstanceConfigurationRoute(transport);

    await route.get();

    expect(transport.requestOptions?.method).toBe("GET");
    expect(transport.requestOptions?.path).toBe(
      "/admin/instance-configuration",
    );
  });

  test("rejects a value whose JSON type disagrees with its declared type", async () => {
    const transport: Transport = {
      request: async <TOut>(options: TransportRequest<TOut>): Promise<TOut> =>
        options.outputSchema?.parse({
          groups: [
            {
              id: "runtime",
              label: "Runtime",
              entries: [
                {
                  variable: "UMBOD_LOG_LEVEL",
                  label: "Log level",
                  description: "Logging level.",
                  type: "boolean",
                  value: "true",
                },
              ],
            },
          ],
        }) as TOut,
    };

    await expect(
      new HttpInstanceConfigurationRoute(transport).get(),
    ).rejects.toThrow();
  });
});
