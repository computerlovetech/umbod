import { afterEach, expect, test, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import { InMemoryAgentBehaviourApi } from '#lib/agent-behaviour/in-memory.test-support.js';
import { AgentBehaviourPageState } from '#lib/agent-behaviour/state/page-state.svelte.js';
import AgentBehaviourView from './AgentBehaviourView.svelte';
import ConfigurationView from './ConfigurationView.svelte';

afterEach((): void => { vi.restoreAllMocks(); });

test('renders findings directly with externally owned state and stops only report reads on exit', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi();
  const state = new AgentBehaviourPageState(api);
  const configurationRead = vi.spyOn(api.configuration, 'get');
  const list = vi.spyOn(api.reports, 'list');
  const target = document.createElement('div'); document.body.append(target);
  const component = mount(AgentBehaviourView, { target, props: { state } }); flushSync();
  try {
    await vi.waitFor((): void => expect(list).toHaveBeenCalledTimes(1));
    expect(target.querySelector('h2')?.textContent).toBe('Agent behaviour');
    expect(target.querySelector('.insight-heading p')).toBeNull();
    expect(target.textContent).not.toContain('Agent self-reported findings · Not independently verified');
    expect(target.querySelector('[role="tablist"]')).toBeNull();
    expect(target.textContent).not.toContain('Reports');
    expect(target.textContent).not.toContain('Add pattern');
    expect(configurationRead).not.toHaveBeenCalled();
  } finally { await unmount(component); target.remove(); }
  expect(state.allowed).toBe(true);
  expect(state.reports.page.items).toEqual([]);
  await state.configuration.load();
  expect(state.configuration.loaded).toBe(true);
  state.dispose();
});

test('configuration owns its backlink and closes the editor on exit without discarding its draft', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi();
  const state = new AgentBehaviourPageState(api);
  await state.configuration.load(); await state.configuration.addPattern();
  const selected = state.configuration.selected;
  expect(selected).toBeDefined();
  state.configuration.updatePattern(selected!.id, 'name', 'Unsaved pattern');
  const target = document.createElement('div'); document.body.append(target);
  const component = mount(ConfigurationView, { target, props: { state: state.configuration } }); flushSync();
  try {
    expect(target.querySelector('h2')?.textContent).toBe('Configuration');
    expect(target.querySelector('a.admin-back-link')?.getAttribute('href')).toBe('/admin/insights/agent-behaviour');
    expect(target.querySelector('dialog')).not.toBeNull();
    expect(target.textContent).not.toContain('Add pattern');
    expect(target.textContent).not.toContain('Restore defaults');
  } finally { await unmount(component); target.remove(); }
  expect(state.configuration.selected).toBeUndefined();
  expect(state.configuration.patterns[0].name).toBe('Unsaved pattern');
  expect(state.configuration.dirty).toBe(true);
  state.dispose();
});

test('revocation clears owned content before notifying its owner exactly once', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi();
  const onAccessLost = vi.fn((): void => {
    expect(state.allowed).toBe(false);
    expect(state.configuration.patterns).toEqual([]);
    expect(state.reports.page.items).toEqual([]);
  });
  const state = new AgentBehaviourPageState(api, onAccessLost);
  await state.configuration.load();
  const target = document.createElement('div'); document.body.append(target);
  const component = mount(AgentBehaviourView, { target, props: { state } }); flushSync();
  try {
    state.revoke(); state.revoke(); flushSync();
    expect(onAccessLost).toHaveBeenCalledTimes(1);
    expect(target.querySelector('[role="alert"]')?.textContent).toContain('Administration access');
    expect(target.querySelector('form')).toBeNull();
  } finally { await unmount(component); target.remove(); state.dispose(); }
});
