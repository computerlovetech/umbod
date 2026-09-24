import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('frontend image configuration', () => {
  it('does not compile public origins into the frontend image', () => {
    const dockerfile = readFileSync(resolve('Dockerfile'), 'utf8');
    expect(dockerfile).not.toMatch(/ARG PUBLIC_(?:API|MCP|SITE)_BASE_URL/);
  });
});
