import { afterEach, expect, test, vi } from 'vitest';
import { createRawSnippet, mount, tick, unmount } from 'svelte';
import { goto } from '$app/navigation';
import { deferred } from '#lib/dashboard/usage-fixtures.test-support.js';
import type { ConnectorCapability } from '#lib/admin/connector-capabilities.js';
import ConnectorCapabilities from './ConnectorCapabilities.svelte';

const feedback = vi.hoisted(() => ({ error: vi.fn() }));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('#lib/components/feedback/index.js', () => ({ useToast: (): object => feedback }));

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  vi.resetAllMocks();
});

function renderCapabilities(): void {
  component = mount(ConnectorCapabilities, {
    target: document.body,
    props: {
      selected: 'tools',
      counts: { tools: 1, prompts: 2, resources: 3 },
      currentUrl: new URL('https://umbod.test/admin/connectors?connector=calendar'),
      children: createRawSnippet<[ConnectorCapability]>(() => ({ render: (): string => '<input aria-label="Draft">' }))
    }
  });
}

function promptsLink(): HTMLAnchorElement {
  const link = document.querySelector<HTMLAnchorElement>('a[href*="capability=prompts"]');
  expect(link).not.toBeNull();
  return link!;
}

test('capability navigation is shallow, retains connector selection and preserves the mounted draft', async (): Promise<void> => {
  const pending = deferred<void>();
  vi.mocked(goto).mockReturnValue(pending.promise);
  renderCapabilities();
  const input = document.querySelector<HTMLInputElement>('input');
  expect(input).not.toBeNull();
  input!.value = 'Unsaved draft';
  promptsLink().click();
  expect(goto).toHaveBeenCalledWith(new URL('https://umbod.test/admin/connectors?connector=calendar&capability=prompts'), { shallow: true, state: {} });
  pending.resolve();
  await vi.waitFor(() => expect(promptsLink().getAttribute('aria-current')).toBe('page'));
  expect(document.querySelector('input')).toBe(input);
  expect(input!.value).toBe('Unsaved draft');
  expect(feedback.error).not.toHaveBeenCalled();
});

test('rejected capability navigation retains the active capability and reports a safe error', async (): Promise<void> => {
  vi.mocked(goto).mockRejectedValue(new Error('Route could not be resolved'));
  renderCapabilities();
  promptsLink().click();
  await tick();
  expect(document.querySelector('a[aria-current="page"]')?.getAttribute('href')).toContain('capability=tools');
  expect(feedback.error).toHaveBeenCalledWith('Could not change connector capability');
});
