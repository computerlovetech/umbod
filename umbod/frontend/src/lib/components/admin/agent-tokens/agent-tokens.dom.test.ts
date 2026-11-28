import { flushSync, mount, tick, unmount } from 'svelte';
import { afterEach, expect, it, vi } from 'vitest';
import type { AgentTokenMetadata, CreateAgentTokenInput, IssuedAgentToken, RotateAgentTokenInput } from '#lib/admin/agent-tokens/domain/schemas.js';
import type { AgentTokens } from '#lib/admin/agent-tokens/port.js';
import AgentTokensWorkspace from './AgentTokensWorkspace.svelte';

vi.mock('#lib/components/feedback/toast-context', () => ({ useToast: () => ({}) }));

const group = { group_id: 'shared-read', label: 'Shared read', description: '', revision: 1 };
const issueTime = Date.parse('2099-05-20T12:30:00Z');
const defaultExpiry = '2099-06-19T12:30:00.000Z';
const createdToken = 'test-issued-secret';
const rotatedToken = 'test-rotated-secret';
const cleanups: Array<() => Promise<void>> = [];

afterEach(async (): Promise<void> => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  vi.restoreAllMocks();
});

function render(api: AgentTokens, groups: typeof group[] = [group], agents: AgentTokenMetadata[] = []): HTMLElement {
  const target = document.createElement('div');
  document.body.append(target);
  const component = mount(AgentTokensWorkspace, { target, props: { api, agents, groups } });
  cleanups.push(async (): Promise<void> => { await unmount(component); target.remove(); });
  flushSync();
  return target;
}

function button(target: ParentNode, label: string): HTMLButtonElement {
  const match = [...target.querySelectorAll('button')].find((element): boolean =>
    (element.getAttribute('aria-label') ?? element.textContent?.trim()) === label
  );
  if (!match) throw new Error(`Missing button: ${label}`);
  return match;
}

function field(target: ParentNode, name: string): HTMLInputElement {
  const input = target.querySelector<HTMLInputElement>(`[name="${name}"]`);
  if (!input) throw new Error(`Missing field: ${name}`);
  return input;
}

function picker(target: ParentNode, label: string): HTMLButtonElement {
  const named = [...target.querySelectorAll('label')].find((item) => item.textContent?.trim() === label);
  const trigger = named && [...target.querySelectorAll<HTMLButtonElement>('[role="combobox"]')].find((item) => item.id === named.htmlFor);
  if (!trigger) throw new Error(`Missing picker: ${label}`);
  return trigger;
}

async function choose(target: ParentNode, label: string, value: string): Promise<void> {
  picker(target, label).click();
  await tick();
  const option = [...target.querySelectorAll<HTMLElement>('[role="option"]')].find((item) => item.textContent?.trim() === value);
  if (!option) throw new Error(`Missing option: ${value}`);
  option.click();
  await tick();
}

function setupApi(): { api: AgentTokens; create: ReturnType<typeof vi.fn<AgentTokens['create']>>; rotate: ReturnType<typeof vi.fn<AgentTokens['rotate']>>; revoke: ReturnType<typeof vi.fn<AgentTokens['revoke']>> } {
  let agents: AgentTokenMetadata[] = [];
  const create = vi.fn(async (input: CreateAgentTokenInput): Promise<IssuedAgentToken> => {
    const metadata: AgentTokenMetadata = { ...input, agent_id: 'a'.repeat(32), credential_id: 'b'.repeat(32), status: 'active' };
    agents = [metadata];
    return { metadata, token: createdToken };
  });
  const rotate = vi.fn(async (agentId: string, input: RotateAgentTokenInput): Promise<IssuedAgentToken> => {
    const previous = agents.find((agent) => agent.agent_id === agentId);
    if (!previous) throw new Error('Agent not found');
    const metadata: AgentTokenMetadata = { ...previous, ...input, credential_id: 'c'.repeat(32), status: 'active' };
    agents = [metadata];
    return { metadata, token: rotatedToken };
  });
  const revoke = vi.fn(async (agentId: string): Promise<void> => {
    agents = agents.map((agent): AgentTokenMetadata => agent.agent_id === agentId ? { ...agent, status: 'revoked' } : agent);
  });
  return { api: { list: async (): Promise<AgentTokenMetadata[]> => agents, create, rotate, revoke }, create, rotate, revoke };
}

it('issues with the default expiration, rotates to Never, and confirms revocation without retaining secrets', async (): Promise<void> => {
  vi.spyOn(Date, 'now').mockReturnValue(issueTime);
  const { api, create, rotate, revoke } = setupApi();
  const target = render(api);
  const list = target.querySelector('[aria-label="Agent tokens"]');
  expect(list?.textContent).toContain('No agent tokens yet.');
  button(target, 'Create agent token').click();
  await tick();
  field(target, 'display_name').value = 'Research worker';
  await choose(target, 'Group', 'Shared read (shared-read)');
  expect(picker(target, 'Expiration').textContent).toContain('30 days');
  button(target, 'Create token').click();
  await vi.waitFor(() => expect(target.querySelector('dialog')?.textContent).toContain(createdToken));
  expect(create).toHaveBeenCalledWith({ display_name: 'Research worker', group_id: group.group_id, expires_at: defaultExpiry });
  expect(list?.textContent).toContain('Group: Shared read');
  expect(list?.textContent).not.toContain(createdToken);
  button(target, 'Done').click();
  await tick();
  expect(target.textContent).not.toContain(createdToken);

  button(target, 'Rotate token for Research worker').click();
  await tick();
  expect(target.querySelectorAll('[role="combobox"]')).toHaveLength(1);
  await choose(target, 'Expiration', 'Never');
  button(target, 'Rotate token').click();
  await vi.waitFor(() => expect(target.querySelector('dialog')?.textContent).toContain(rotatedToken));
  expect(rotate).toHaveBeenCalledWith('a'.repeat(32), { expires_at: null });
  expect(list?.textContent).toContain('Never expires');
  button(target, 'Done').click();
  await tick();
  expect(target.textContent).not.toContain(rotatedToken);

  button(target, 'Revoke token for Research worker').click();
  await tick();
  expect(target.querySelector('dialog')?.textContent).toContain('a'.repeat(32));
  expect(revoke).not.toHaveBeenCalled();
  button(target, 'Revoke token').click();
  await vi.waitFor(() => expect(list?.textContent).toContain('revoked'));
  expect(revoke).toHaveBeenCalledWith('a'.repeat(32));
  expect(target.querySelector('dialog')).toBeNull();
});

it('requires a group even when creating an agent token that never expires', async (): Promise<void> => {
  const { api, create } = setupApi();
  const missingGroups = render(api, []);
  expect(button(missingGroups, 'Create agent token').disabled).toBe(true);
  const target = render(api);
  button(target, 'Create agent token').click();
  await tick();
  field(target, 'display_name').value = 'Research worker';
  await choose(target, 'Expiration', 'Never');
  button(target, 'Create token').click();
  await tick();
  expect(target.querySelector('[role="alert"]')?.textContent).toContain('select a group');
  expect(create).not.toHaveBeenCalled();
  await choose(target, 'Group', 'Shared read (shared-read)');
  button(target, 'Create token').click();
  await vi.waitFor(() => expect(create).toHaveBeenCalledWith({ display_name: 'Research worker', group_id: group.group_id, expires_at: null }));
});

it('marks a token expired while the inventory remains open', async (): Promise<void> => {
  vi.useFakeTimers();
  try {
    vi.setSystemTime(new Date('2099-01-01T12:00:00Z'));
    const { api } = setupApi();
    const { metadata } = await api.create({ display_name: 'Research worker', group_id: group.group_id, expires_at: '2099-01-01T12:00:10Z' });
    const target = render(api, [group], [metadata]);
    expect(target.textContent).toContain('active');
    vi.advanceTimersByTime(15_000);
    await tick();
    expect(target.textContent).toContain('expired');
  } finally {
    vi.useRealTimers();
  }
});
