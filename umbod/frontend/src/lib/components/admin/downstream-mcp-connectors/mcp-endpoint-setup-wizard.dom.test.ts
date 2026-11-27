import { mount, tick, unmount } from 'svelte';
import { expect, test, vi } from 'vitest';
import McpEndpointSetupWizard from './McpEndpointSetupWizard.svelte';
import { McpEndpointSetupState } from './mcp-endpoint-setup-state.svelte';

function button(target: HTMLElement, label: string): HTMLButtonElement {
  const control = [...target.querySelectorAll('button')].find((item) => item.textContent?.trim() === label);
  if (!control) throw new Error(`Missing button: ${label}`);
  return control;
}

test('closing unverified access clears its selection and disables continuation', async (): Promise<void> => {
  const state = new McpEndpointSetupState({
    api: () => ({
      search: vi.fn(),
      checkAccess: async () => ({
        anonymous_initialization: { kind: 'anonymous_access_rejected', status_code: 401 },
        oauth: { kind: 'oauth_not_confirmed' }
      })
    }),
    personalAvailable: () => true,
    accessLost: vi.fn(),
    complete: vi.fn()
  });
  state.openManual();
  state.changeManualUrl('https://mcp.example.com/mcp');
  await state.checkAccess();

  const target = document.createElement('div');
  document.body.append(target);
  const wizard = mount(McpEndpointSetupWizard, { target, props: { state, close: vi.fn() } });
  try {
    await tick();
    const disclosure = button(target, 'Unverified access methods');
    const next = button(target, 'Next: Configure');
    const unverifiedChoice = (): HTMLInputElement | null => target.querySelector('.unverified-choices input');
    expect(disclosure.getAttribute('aria-expanded')).toBe('false');
    expect(unverifiedChoice()).toBeNull();
    expect(next.disabled).toBe(true);

    disclosure.click();
    await tick();
    expect(disclosure.getAttribute('aria-expanded')).toBe('true');
    const choice = unverifiedChoice();
    if (!choice) throw new Error('Missing unverified access option');
    choice.click();
    await tick();
    expect(next.disabled).toBe(false);

    choice.focus();
    disclosure.click();
    await tick();
    expect(disclosure.getAttribute('aria-expanded')).toBe('false');
    expect(unverifiedChoice()).toBeNull();
    expect(next.disabled).toBe(true);
    expect(document.activeElement).toBe(disclosure);

    disclosure.click();
    await tick();
    expect(unverifiedChoice()?.checked).toBe(false);
  } finally {
    await unmount(wizard);
    target.remove();
  }
});
