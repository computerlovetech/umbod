export type TelemetryAgent = 'codex' | 'claude-code';

export function telemetryConfiguration(agent: TelemetryAgent, endpoint: string, token: string): string {
  if (agent === 'codex') {
    return '[analytics]\nenabled = false\n\n[otel]\nlog_user_prompt = false\nlog_agent_responses = false\nlog_guardian_assessments = false\ntrace_exporter = "none"\nmetrics_exporter = "none"\n\n[otel.exporter.otlp-http]\nendpoint = ' + JSON.stringify(endpoint) + '\nprotocol = "json"\nheaders = { Authorization = ' + JSON.stringify('Bearer ' + token) + ' }';
  }
  return JSON.stringify({ env: {
    CLAUDE_CODE_ENABLE_TELEMETRY: '1',
    OTEL_LOGS_EXPORTER: 'otlp',
    OTEL_EXPORTER_OTLP_LOGS_PROTOCOL: 'http/json',
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT: endpoint,
    OTEL_EXPORTER_OTLP_LOGS_HEADERS: 'Authorization=Bearer ' + token,
    OTEL_METRICS_EXPORTER: 'none',
    OTEL_TRACES_EXPORTER: 'none',
    OTEL_LOG_USER_PROMPTS: '0',
    OTEL_LOG_ASSISTANT_RESPONSES: '0',
    OTEL_LOG_TOOL_DETAILS: '0',
    OTEL_LOG_TOOL_CONTENT: '0',
    OTEL_LOG_RAW_API_BODIES: '0'
  } }, null, 2);
}
