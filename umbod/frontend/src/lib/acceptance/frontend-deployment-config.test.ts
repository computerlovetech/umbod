import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const EXPECTED_BODY_SIZE_LIMIT = '12M';

function deploymentConfiguration(filename: string): string {
  return readFileSync(resolve('..', filename), 'utf8');
}

describe('frontend deployment configuration', () => {
  it('does not compile public origins into the frontend image', () => {
    const dockerfile = readFileSync(resolve('Dockerfile'), 'utf8');
    expect(dockerfile).not.toMatch(/ARG PUBLIC_(?:API|MCP|SITE)_BASE_URL/);

    for (const filename of ['docker-compose.yml', 'docker-compose.production.yml']) {
      const configuration = deploymentConfiguration(filename);
      expect(configuration).not.toMatch(/args:\s*[\s\S]*PUBLIC_(?:API|MCP|SITE)_BASE_URL/);
      expect(configuration).toMatch(/environment:[\s\S]*PUBLIC_MCP_BASE_URL/);
      expect(configuration).toMatch(/environment:[\s\S]*ORIGIN/);
      expect(configuration).toMatch(/environment:[\s\S]*PRIVATE_API_BASE_URL/);
    }
  });

  it.each(['docker-compose.yml', 'docker-compose.production.yml'])(
    'sets a bounded adapter-node body size limit in %s',
    (filename: string) => {
      const configuration = deploymentConfiguration(filename);
      expect(configuration).toMatch(new RegExp(`BODY_SIZE_LIMIT(?:=|:)\\s*${EXPECTED_BODY_SIZE_LIMIT}\\b`));
      expect(configuration).not.toMatch(/BODY_SIZE_LIMIT(?:=|:)\s*(?:Infinity|0)\b/);
    }
  );
});
