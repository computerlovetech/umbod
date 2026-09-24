import { randomBytes } from 'node:crypto';

const severityNumbers = {
  debug: 5,
  info: 9,
  warning: 13,
  error: 17,
  critical: 21
} as const;

export type LogSeverity = keyof typeof severityNumbers;
export type LogAttributes = Readonly<Record<string, unknown>>;

export type StructuredLogRecord = {
  body: string;
  severity: LogSeverity;
  attributes?: LogAttributes;
  traceId?: string;
  spanId?: string;
  error?: unknown;
};

type LogPayload = {
  timestamp: number;
  observed_timestamp: number;
  severity_text: string;
  severity_number: number;
  body: string;
  attributes: Record<string, unknown>;
  resource: { 'service.name': string };
  trace_id?: string;
  span_id?: string;
};

const configuredLevel = parseLogSeverity(process.env.UMBOD_LOG_LEVEL);
const serviceName = process.env.UMBOD_FRONTEND_SERVICE_NAME?.trim() || 'umbod-frontend';

export function emitStructuredLog(record: StructuredLogRecord): void {
  if (severityNumbers[record.severity] < severityNumbers[configuredLevel]) {
    return;
  }
  const timestamp = Date.now() * 1_000_000;
  const payload: LogPayload = {
    timestamp,
    observed_timestamp: timestamp,
    severity_text: record.severity.toUpperCase(),
    severity_number: severityNumbers[record.severity],
    body: record.body,
    attributes: {
      'logger.name': 'umbod.frontend',
      ...normalizeAttributes(record.attributes ?? {}),
      ...exceptionAttributes(record.error)
    },
    resource: { 'service.name': serviceName }
  };
  if (record.traceId) {
    payload.trace_id = record.traceId;
  }
  if (record.spanId) {
    payload.span_id = record.spanId;
  }
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

export function requestTraceContext(request: Request): { traceId: string; spanId: string } {
  const traceId = parseTraceId(request.headers.get('traceparent')) ?? randomHex(16);
  return { traceId, spanId: randomHex(8) };
}

function parseLogSeverity(value: string | undefined): LogSeverity {
  const normalized = value?.trim().toLowerCase();
  return normalized && normalized in severityNumbers ? (normalized as LogSeverity) : 'info';
}

function parseTraceId(traceparent: string | null): string | null {
  if (!traceparent) {
    return null;
  }
  const match = /^[\da-f]{2}-([\da-f]{32})-[\da-f]{16}-[\da-f]{2}$/i.exec(traceparent.trim());
  if (!match || /^0+$/.test(match[1])) {
    return null;
  }
  return match[1].toLowerCase();
}

function randomHex(byteLength: number): string {
  return randomBytes(byteLength).toString('hex');
}

function normalizeAttributes(attributes: LogAttributes): Record<string, unknown> {
  return Object.fromEntries(Object.entries(attributes).map(([key, value]) => [key, normalizeValue(value)]));
}

function normalizeValue(value: unknown): unknown {
  if (value === null || ['string', 'number', 'boolean'].includes(typeof value)) {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map(normalizeValue);
  }
  if (typeof value === 'object') {
    return normalizeAttributes(value as Record<string, unknown>);
  }
  return String(value);
}

function exceptionAttributes(error: unknown): Record<string, unknown> {
  if (!(error instanceof Error)) {
    return error === undefined ? {} : { 'exception.type': 'Error', 'exception.message': String(error) };
  }
  return {
    'exception.type': error.name,
    'exception.message': error.message,
    ...(error.stack ? { 'exception.stacktrace': error.stack } : {})
  };
}
