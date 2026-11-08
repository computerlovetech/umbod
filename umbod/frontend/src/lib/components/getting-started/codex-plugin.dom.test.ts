import { afterEach, expect, test, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import type { ToastApi } from '$lib/components/feedback/toast-state.svelte';
import { InMemoryCodexPluginDownloader, InMemoryCodexPluginPackager } from '$lib/codex-plugin/in-memory.test-support';
import McpSetupGuide from './McpSetupGuide.svelte';

vi.mock('$lib/components/feedback', () => ({
  useToast: (): ToastApi => ({
    success: (): number => 1, warning: (): number => 1, error: (): number => 1,
    dismiss: (): void => {}
  })
}));

const cleanups: Array<() => Promise<void>> = [];

afterEach(async (): Promise<void> => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  vi.restoreAllMocks();
});

function render(packager: InMemoryCodexPluginPackager, downloader: InMemoryCodexPluginDownloader): HTMLDivElement {
  const target = document.createElement('div');
  document.body.append(target);
  const component = mount(McpSetupGuide, {
    target,
    props: { mcpEndpoint: 'https://umbod.test/team/mcp', pluginPackager: packager, pluginDownloader: downloader }
  });
  cleanups.push(async (): Promise<void> => { await unmount(component); target.remove(); });
  flushSync();
  return target;
}

function downloadButton(target: ParentNode): HTMLButtonElement {
  const button = target.querySelector<HTMLButtonElement>('button[aria-label="Download Codex plugin"]');
  if (!button) throw new Error('Missing plugin download button');
  return button;
}

test('downloading reveals a copyable marketplace command without assuming a ZIP location', async (): Promise<void> => {
  const packager = new InMemoryCodexPluginPackager();
  const downloader = new InMemoryCodexPluginDownloader();
  const target = render(packager, downloader);
  expect(target.querySelector('button[aria-label="Copy codex plugin marketplace add ."]')).toBeNull();
  downloadButton(target).click();
  await vi.waitFor((): void => expect(downloader.downloads).toHaveLength(1));
  expect(downloader.downloads[0].endpoint).toBe('https://umbod.test/team/mcp');
  expect(target.textContent).toContain('umbod-codex-0123456789ab.zip');
  expect(target.textContent).toContain('Extract the ZIP to a folder you want to keep');
  expect(target.textContent).toContain('/plugins');
  expect(target.textContent).not.toContain('~/Downloads');
  expect(target.textContent).not.toContain('mktemp');
  expect(target.textContent).not.toContain('unzip');
  const copy = target.querySelector<HTMLButtonElement>('button[aria-label="Copy codex plugin marketplace add ."]');
  if (!copy) throw new Error('Missing installation command copy button');
  const clipboard = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
  copy.click();
  await vi.waitFor((): void => expect(clipboard).toHaveBeenCalledWith('codex plugin marketplace add .'));
  expect(downloadButton(target).disabled).toBe(false);
  const manual = target.querySelector('details');
  expect(manual).not.toBeNull();
  expect(manual?.textContent).toContain('codex mcp add umbod --url');
  expect(target.textContent).toContain('Claude Code');
});

test('a failed download displays an actionable error and allows retry', async (): Promise<void> => {
  const packager = new InMemoryCodexPluginPackager();
  packager.failure = new Error('private diagnostic');
  const downloader = new InMemoryCodexPluginDownloader();
  const target = render(packager, downloader);
  downloadButton(target).click();
  await vi.waitFor((): void => expect(target.querySelector('[role="alert"]')?.textContent).toContain('Could not download'));
  expect(target.textContent).not.toContain('private diagnostic');
  expect(target.querySelector('button[aria-label="Copy codex plugin marketplace add ."]')).toBeNull();
  packager.failure = null;
  downloadButton(target).click();
  await vi.waitFor((): void => expect(downloader.downloads).toHaveLength(1));
  expect(target.querySelector('[role="alert"]')).toBeNull();
});
