import { expect, it } from 'vitest';
import { telemetrySetupSchema } from './schemas';

it.each([
  { status: 'available', logs_endpoint: 'https://collector.example:9443/prefix/v1/logs' },
  { status: 'unavailable', reason: 'disabled' },
  { status: 'unavailable', reason: 'not_configured' }
])('accepts the setup response $status', (value): void => {
  expect(telemetrySetupSchema.parse(value)).toEqual(value);
});

it.each([
  {},
  { status: 'available' },
  { status: 'available', logs_endpoint: 'not-a-url' },
  { status: 'available', logs_endpoint: 'ftp://collector.example/v1/logs' },
  { status: 'unavailable', reason: 'unknown' },
  { status: 'unavailable', reason: 'disabled', logs_endpoint: 'https://collector.example/v1/logs' }
])('rejects malformed setup responses', (value): void => {
  expect(telemetrySetupSchema.safeParse(value).success).toBe(false);
});
