import { render } from 'svelte/server';
import { expect, test } from 'vitest';
import McpSetupGuide from './McpSetupGuide.svelte';

test('renders the initial wizard step without an eager install or a second page heading', (): void => {
  const { body } = render(McpSetupGuide, { props: { installerBaseUrl: 'https://site.test/api/install/v1' } });
  expect(body).not.toContain('<h1');
  expect(body).toContain('aria-label="Installer steps"');
  expect(body).toContain('aria-current="step"');
  expect(body).toContain('Choose your platform');
  expect(body).toContain('Review and install');
  for (const platform of ['macOS', 'Linux', 'Windows']) expect(body).toContain(platform);
  expect(body).not.toContain('install.sh');
});
