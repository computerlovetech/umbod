import { describe, expect, it } from 'vitest';
import { connectorInitials } from './connector-icon';

describe('connectorInitials', () => {
  it.each([
    ['GitHub', 'GI'],
    ['MCP Proxy', 'MP'],
    ['  Linear API  ', 'LA'],
    ['', '?']
  ])('creates a compact fallback for %j', (label, expected) => {
    expect(connectorInitials(label)).toBe(expected);
  });
});
