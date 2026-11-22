import { expect, it } from 'vitest';
import { telemetryConfiguration } from './telemetry-formatters';

it('generates logs-only settings with prompt collection disabled', (): void => {
  const codex = telemetryConfiguration('codex', 'https://collector.example/v1/logs', 'secret');
  expect(codex).toContain('[otel]');
  expect(codex).toContain('[analytics]\nenabled = false');
  expect(codex).toContain('log_user_prompt = false');
  expect(codex).toContain('log_agent_responses = false');
  expect(codex).toContain('log_guardian_assessments = false');
  expect(codex).toContain('trace_exporter = "none"');
  expect(codex).toContain('metrics_exporter = "none"');
  expect(codex).toContain('[otel.exporter.otlp-http]');
  expect(codex).toContain('protocol = "json"');
  expect(codex).toContain('Authorization = "Bearer secret"');
  const claude = JSON.parse(telemetryConfiguration('claude-code', 'https://collector.example/v1/logs', 'secret'));
  expect(claude.env).toMatchObject({ OTEL_LOGS_EXPORTER: 'otlp', OTEL_METRICS_EXPORTER: 'none', OTEL_TRACES_EXPORTER: 'none', OTEL_LOG_USER_PROMPTS: '0', OTEL_LOG_ASSISTANT_RESPONSES: '0', OTEL_LOG_TOOL_DETAILS: '0', OTEL_LOG_TOOL_CONTENT: '0', OTEL_LOG_RAW_API_BODIES: '0', OTEL_EXPORTER_OTLP_LOGS_PROTOCOL: 'http/json', OTEL_EXPORTER_OTLP_LOGS_ENDPOINT: 'https://collector.example/v1/logs', OTEL_EXPORTER_OTLP_LOGS_HEADERS: 'Authorization=Bearer secret' });
  expect(claude.env).not.toHaveProperty('OTEL_EXPORTER_OTLP_PROTOCOL');
});
