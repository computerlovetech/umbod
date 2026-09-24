import { describe, expect, test } from 'vitest';
import { HttpError, NetworkError } from './infrastructure/transport';
import { parseDownstreamMcpError, presentDownstreamMcpActionError } from './downstream-mcp-errors';

const envelope = (code: string, phase = 'validation') => ({ detail: { code, message: 'safe server message', phase, retryable: false, context: {} } });

describe('downstream MCP REST error presenter', () => {
  test.each([
    ['endpoint_not_found', 422, 'No MCP server was found'],
    ['public_path_conflict', 409, 'public path'],
    ['connector_not_found', 404, 'no longer exists']
  ])('presents %s without using server message', (code, status, expected) => {
    const result = presentDownstreamMcpActionError(new HttpError(status, 'Failed', envelope(code)), 'Operation');
    expect(result.statusCode).toBe(status);
    expect(result.data.message).toContain(expected);
    expect(result.data.message).not.toContain('safe server message');
  });

  test.each([null, {}, { detail: 'secret=exposed' }, envelope('unknown_code')])('uses a safe fallback for malformed or unknown envelopes', (body) => {
    expect(parseDownstreamMcpError(body)).toBeUndefined();
    const result = presentDownstreamMcpActionError(new HttpError(502, 'Failed', body), 'Discovery');
    expect(result.data.message).toBe('Discovery failed. Try again.');
    expect(result.data.message).not.toContain('secret');
  });

  test('uses a safe network fallback for network failures', () => {
    expect(presentDownstreamMcpActionError(new NetworkError(new Error('token=secret')), 'Discovery')).toEqual({ statusCode: 503, data: { status: 'network', message: 'Discovery could not reach the connector service. Try again.' } });
  });

  test('rethrows unexpected implementation failures', () => {
    expect(() => presentDownstreamMcpActionError(new Error('implementation failure'), 'Discovery')).toThrow('implementation failure');
  });
});
