import { z } from 'zod';

export const telemetrySetupSchema = z.discriminatedUnion('status', [
  z.strictObject({ status: z.literal('available'), logs_endpoint: z.url({ protocol: /^https?$/ }) }),
  z.strictObject({ status: z.literal('unavailable'), reason: z.enum(['disabled', 'not_configured']) })
]);

export const telemetryHarnessSchema = z.enum(['codex', 'claude-code']);
export const telemetryInstallClaimRequestSchema = z.strictObject({ harness: telemetryHarnessSchema });
export const telemetryInstallClaimSchema = z.strictObject({ code: z.string().length(43).regex(/^[A-Za-z0-9_-]{43}$/) });

export type TelemetrySetup = z.infer<typeof telemetrySetupSchema>;
export type TelemetryInstallClaimRequest = z.infer<typeof telemetryInstallClaimRequestSchema>;
export type TelemetryInstallClaim = z.infer<typeof telemetryInstallClaimSchema>;
