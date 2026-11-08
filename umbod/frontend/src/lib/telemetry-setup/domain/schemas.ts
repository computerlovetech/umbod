import { z } from 'zod';

export const telemetrySetupSchema = z.discriminatedUnion('status', [
  z.strictObject({ status: z.literal('available'), logs_endpoint: z.url({ protocol: /^https?$/ }) }),
  z.strictObject({ status: z.literal('unavailable'), reason: z.enum(['disabled', 'not_configured']) })
]);

export type TelemetrySetup = z.infer<typeof telemetrySetupSchema>;
