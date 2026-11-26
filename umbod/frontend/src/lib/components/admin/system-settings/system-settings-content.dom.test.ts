import type { beforeNavigate as registerBeforeNavigate } from '$app/navigation';
import { flushSync, mount, tick, unmount } from 'svelte';
import { fromStore, writable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';
import { HttpError } from '#lib/admin/infrastructure/transport.js';
import type { FilesystemSettings } from '#lib/admin/system-settings/domain/filesystem-settings.js';
import type { FilesystemSettingsAdministration } from '#lib/admin/system-settings/filesystem-settings-port.js';
import { deferred, InMemoryAgentBehaviourApi } from '#lib/agent-behaviour/in-memory.test-support.js';
import type { Configuration } from '#lib/agent-behaviour/domain/schemas.js';
import SystemSettingsContent from './SystemSettingsContent.svelte';

type BeforeNavigate = Parameters<Parameters<typeof registerBeforeNavigate>[0]>[0];

const { beforeNavigate } = vi.hoisted(() => ({ beforeNavigate: vi.fn<typeof registerBeforeNavigate>() }));
vi.mock('$app/navigation', () => ({ beforeNavigate }));

const origin = 'http://localhost:3010';
const settingsPath = '/admin/system-settings';
const reportingPath = `${settingsPath}?section=agent-diagnostics`;
const patternsPath = '/admin/agent-diagnostics';

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  beforeNavigate.mockClear();
});

function configuredDiagnostics(): InMemoryAgentBehaviourApi {
  const api = new InMemoryAgentBehaviourApi();
  api.current = {
    revision: 1,
    patterns: [{ id: 'context', name: 'Missing context', description: 'Notice missing facts', assessment_prompt: 'Assess missing facts', inclusion_criteria: '', exclusion_criteria: '', categories: [], polarity: 'neutral', enabled: true }],
    playbooks: [{ id: 'review', name: 'Behaviour review', collection_instructions: 'Collect facts', pattern_ids: ['context'], enabled: true, allow_proactive: false }]
  };
  return api;
}

const filesystemValue: FilesystemSettings = { require_mcp_file_deletion_approval: { value: true, source: 'built_in_default' } };

function mountSettings(api: InMemoryAgentBehaviourApi, path: string, get: FilesystemSettingsAdministration['get'] = async () => filesystemValue): (nextPath: string) => void {
  const current = writable(new URL(path, origin).searchParams);
  const query = fromStore(current);
  const filesystemSettings: FilesystemSettingsAdministration = { get, update: async () => filesystemValue };
  component = mount(SystemSettingsContent, {
    target: document.body,
    props: { get query(): URLSearchParams { return query.current; }, filesystemSettings, diagnosticsConfiguration: api.configuration }
  });
  return (nextPath: string): void => current.set(new URL(nextPath, origin).searchParams);
}

function element<T extends HTMLElement>(selector: string): T {
  const match = document.querySelector<T>(selector);
  if (!match) throw new Error(`Missing element: ${selector}`);
  return match;
}

function findButton(label: string): HTMLButtonElement | undefined {
  return [...document.querySelectorAll('button')].find((candidate): boolean => candidate.textContent?.trim() === label);
}

function button(label: string): HTMLButtonElement {
  const match = findButton(label);
  if (!match) throw new Error(`Missing button: ${label}`);
  return match;
}

function openInstructions(): HTMLTextAreaElement {
  button('Edit instructions').click();
  flushSync();
  return element<HTMLTextAreaElement>('textarea');
}

function changeInstructions(value: string): void {
  const input = openInstructions();
  input.value = value;
  input.dispatchEvent(new Event('input', { bubbles: true }));
}

function navigation(from: string, to: string | null, type: 'link' | 'popstate' | 'leave'): BeforeNavigate {
  const target = (path: string): NonNullable<BeforeNavigate['to']> => ({
    params: {},
    route: { id: path === patternsPath ? '/admin/(agent-insights)/agent-diagnostics' : settingsPath },
    url: new URL(path, origin),
    scroll: null
  });
  const details = { from: target(from), to: to ? target(to) : null, willUnload: !to, shallow: false, complete: Promise.resolve(), cancel: vi.fn() };
  if (type === 'link') return { ...details, type, event: new PointerEvent('click') };
  if (type === 'popstate') return { ...details, type, delta: -1, event: new PopStateEvent('popstate') };
  return { ...details, type };
}

test('loads diagnostics once on first visit and preserves both drafts across sections', async (): Promise<void> => {
  const api = configuredDiagnostics();
  const get = vi.spyOn(api.configuration, 'get');
  const navigate = mountSettings(api, settingsPath);
  const toggle = 'input[aria-label="Require approval for MCP file deletion"]';
  await vi.waitFor(() => expect(element<HTMLInputElement>(toggle).checked).toBe(true));
  expect(get).not.toHaveBeenCalled();
  element<HTMLInputElement>(toggle).click();

  navigate(reportingPath);
  await vi.waitFor(() => expect(document.body.textContent).toContain('Collect facts'));
  expect(document.querySelector(toggle)).toBeNull();
  expect(element('aside a[aria-current="location"]').textContent).toContain('Reporting settings');
  expect(element(`a[href="${patternsPath}"]`).textContent).toContain('Manage patterns');
  changeInstructions('Draft collection instructions');
  navigate(settingsPath);
  await tick();
  expect(element<HTMLInputElement>(toggle).checked).toBe(false);
  expect(button('Save changes').disabled).toBe(false);

  navigate(reportingPath);
  await tick();
  expect(document.body.textContent).toContain('Draft collection instructions');
  expect(openInstructions().value).toBe('Draft collection instructions');
  expect(button('Save changes').disabled).toBe(false);
  expect(get).toHaveBeenCalledTimes(1);
});

test('opens instructions on demand and keeps the draft when the editor is closed', async (): Promise<void> => {
  const api = configuredDiagnostics();
  const publish = vi.spyOn(api.configuration, 'publish');
  mountSettings(api, reportingPath);
  await vi.waitFor(() => expect(document.body.textContent).toContain('Collect facts'));
  expect(document.querySelector('textarea')).toBeNull();
  expect(button('Edit instructions').getAttribute('aria-expanded')).toBe('false');
  expect(findButton('Save changes')).toBeUndefined();
  expect(findButton('Discard changes')).toBeUndefined();

  changeInstructions('Collect facts, not guesses');
  await tick();
  expect(button('Close editor').getAttribute('aria-expanded')).toBe('true');
  button('Close editor').click();
  await tick();
  expect(document.querySelector('textarea')).toBeNull();
  expect(document.body.textContent).toContain('Collect facts, not guesses');
  const save = button('Save changes');
  const reporting = element('[aria-labelledby="reporting-settings-title"]');
  expect(save.disabled).toBe(false);
  expect(reporting.compareDocumentPosition(save) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(reporting.contains(save)).toBe(false);
  expect(publish).not.toHaveBeenCalled();

  button('Discard changes').click();
  await tick();
  expect(document.body.textContent).not.toContain('Collect facts, not guesses');
  expect(findButton('Save changes')).toBeUndefined();
  expect(findButton('Discard changes')).toBeUndefined();
  expect(openInstructions().value).toBe('Collect facts');
});

test('directs administrators to pattern management when reporting has not been configured', async (): Promise<void> => {
  mountSettings(new InMemoryAgentBehaviourApi(), reportingPath);
  await vi.waitFor(() => expect(document.body.textContent).toContain('No reporting settings configured.'));
  expect(element(`a[href="${patternsPath}"]`).textContent).toContain('Manage patterns');
  expect(document.querySelector('textarea')).toBeNull();
  expect(findButton('Save changes')).toBeUndefined();
  expect(findButton('Discard changes')).toBeUndefined();
});

test('finishes saving from a direct Reporting settings URL while Filesystem is showing', async (): Promise<void> => {
  const api = configuredDiagnostics();
  const saved = deferred<Configuration>();
  const publish = vi.spyOn(api.configuration, 'publish').mockReturnValue(saved.promise);
  const navigate = mountSettings(api, reportingPath);
  await vi.waitFor(() => expect(document.body.textContent).toContain('Collect facts'));
  expect(element('[aria-labelledby="reporting-settings-title"]').textContent).toContain('Reporting settings');
  expect(document.querySelector('[aria-labelledby="diagnostic-patterns-title"]')).toBeNull();
  expect(document.body.textContent).not.toContain('Add pattern');
  expect(element(`a[href="${patternsPath}"]`).textContent).toContain('Manage patterns');

  changeInstructions('Saved instructions');
  await tick();
  button('Save changes').click();
  expect(publish).toHaveBeenCalledExactlyOnceWith({
    expected_revision: api.current.revision,
    patterns: api.current.patterns,
    playbooks: [{ ...api.current.playbooks[0], collection_instructions: 'Saved instructions' }]
  }, expect.any(AbortSignal));
  const request = publish.mock.calls[0]?.[1];
  expect(request).toBeInstanceOf(AbortSignal);
  await tick();
  expect(button('Save changes').disabled).toBe(true);
  expect(button('Discard changes').disabled).toBe(true);
  navigate(settingsPath);
  await tick();
  expect(request?.aborted).toBe(false);
  saved.resolve({ ...api.current, revision: 2, playbooks: [{ ...api.current.playbooks[0], collection_instructions: 'Saved instructions' }] });
  navigate(reportingPath);
  await vi.waitFor(() => expect(document.body.textContent).toContain('Changes saved'));
  expect(document.body.textContent).toContain('Saved instructions');
  expect(openInstructions().value).toBe('Saved instructions');
  expect(findButton('Save changes')).toBeUndefined();
  expect(findButton('Discard changes')).toBeUndefined();
});

test('confirms departure to pattern management only when reporting changes are unsaved', async (): Promise<void> => {
  const confirm = vi.fn<Window['confirm']>().mockReturnValue(false);
  vi.stubGlobal('confirm', confirm);
  mountSettings(configuredDiagnostics(), reportingPath);
  await vi.waitFor(() => expect(document.body.textContent).toContain('Collect facts'));
  const guard = beforeNavigate.mock.lastCall?.[0];
  if (!guard) throw new Error('Missing navigation guard');

  const cleanDeparture = navigation(reportingPath, patternsPath, 'link');
  guard(cleanDeparture);
  expect(cleanDeparture.cancel).not.toHaveBeenCalled();
  expect(confirm).not.toHaveBeenCalled();
  changeInstructions('Unsaved instructions');

  const switchSection = navigation(reportingPath, settingsPath, 'popstate');
  guard(switchSection);
  expect(switchSection.cancel).not.toHaveBeenCalled();
  expect(confirm).not.toHaveBeenCalled();

  const stay = navigation(reportingPath, patternsPath, 'link');
  guard(stay);
  expect(confirm).toHaveBeenCalledTimes(1);
  expect(stay.cancel).toHaveBeenCalledTimes(1);
  confirm.mockReturnValue(true);
  const departure = navigation(reportingPath, patternsPath, 'link');
  guard(departure);
  expect(departure.cancel).not.toHaveBeenCalled();
  const unload = navigation(reportingPath, null, 'leave');
  guard(unload);
  expect(unload.cancel).toHaveBeenCalledTimes(1);
  expect(confirm).toHaveBeenCalledTimes(2);
});

test('clears the diagnostics draft and hides its navigation after the diagnostics API reports access loss', async (): Promise<void> => {
  const api = configuredDiagnostics();
  vi.spyOn(api.configuration, 'publish').mockRejectedValue(new HttpError(403, 'Forbidden', null));
  const navigate = mountSettings(api, reportingPath);
  await vi.waitFor(() => expect(document.body.textContent).toContain('Collect facts'));
  changeInstructions('Unsaved instructions');
  await tick();
  button('Save changes').click();

  await vi.waitFor(() => expect(element('[role="alert"]').textContent).toContain('Administration access is no longer available'));
  expect(document.querySelector(`textarea, a[href="${patternsPath}"], a[href="${reportingPath}"]`)).toBeNull();
  expect(document.body.textContent).not.toContain('Unsaved instructions');
  navigate(settingsPath);
  await tick();
  expect(element<HTMLInputElement>('input[aria-label="Require approval for MCP file deletion"]').checked).toBe(true);
});

test('still allows diagnostics configuration when the Filesystem API denies access', async (): Promise<void> => {
  const navigate = mountSettings(configuredDiagnostics(), settingsPath, async (): Promise<FilesystemSettings> => {
    throw new HttpError(403, 'Forbidden', null);
  });
  await vi.waitFor(() => expect(element('[role="alert"]').textContent).toContain('You do not have permission'));
  expect(document.querySelector('input[type="checkbox"]')).toBeNull();

  navigate(reportingPath);
  await vi.waitFor(() => expect(document.body.textContent).toContain('Collect facts'));
  expect(element(`a[href="${patternsPath}"]`).textContent).toContain('Manage patterns');
});

test('aborts diagnostics work when the identity-scoped content is destroyed', async (): Promise<void> => {
  const api = configuredDiagnostics();
  const pending = deferred<Configuration>();
  const get = vi.spyOn(api.configuration, 'get').mockReturnValue(pending.promise);
  mountSettings(api, reportingPath);
  await tick();
  const request = get.mock.calls[0]?.[0];
  expect(request?.aborted).toBe(false);
  if (!component) throw new Error('Missing settings component');
  await unmount(component);
  component = undefined;
  expect(request?.aborted).toBe(true);
  pending.resolve(api.current);
  await tick();
  expect(document.querySelector('section[aria-label="System settings workspace"]')).toBeNull();
});
