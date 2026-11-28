import type { beforeNavigate as registerBeforeNavigate } from '$app/navigation';
import { flushSync, mount, tick, unmount } from 'svelte';
import { fromStore, writable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';
import type { GroupCatalogue } from '#lib/admin/groups/port.js';
import { HttpError } from '#lib/admin/infrastructure/transport.js';
import type { FilesystemSettings } from '#lib/admin/system-settings/domain/filesystem-settings.js';
import type { FilesystemSettingsAdministration } from '#lib/admin/system-settings/filesystem-settings-port.js';
import type { ProviderGroupMappings } from '#lib/admin/system-settings/domain/provider-group-mappings.js';
import type { ProviderGroupMappingsAdministration } from '#lib/admin/system-settings/provider-group-mappings-port.js';
import { deferred, InMemoryAgentBehaviourApi } from '#lib/agent-behaviour/in-memory.test-support.js';
import type { Configuration } from '#lib/agent-behaviour/domain/schemas.js';
import SystemSettingsContent from './SystemSettingsContent.svelte';

type BeforeNavigate = Parameters<Parameters<typeof registerBeforeNavigate>[0]>[0];

const { beforeNavigate } = vi.hoisted(() => ({ beforeNavigate: vi.fn<typeof registerBeforeNavigate>() }));
vi.mock('$app/navigation', () => ({ beforeNavigate }));

const origin = 'http://localhost:3010';
const settingsPath = '/admin/system-settings';
const reportingPath = `${settingsPath}?section=agent-diagnostics`;
const mappingsPath = `${settingsPath}?section=provider-group-mappings`;
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
    reporting_enabled: false,
    patterns: [{ id: 'context', name: 'Missing context', description: 'Notice missing facts', assessment_prompt: 'Assess missing facts', inclusion_criteria: '', exclusion_criteria: '', categories: [], polarity: 'neutral', enabled: true }],
    playbooks: [{ id: 'review', name: 'Behaviour review', collection_instructions: 'Collect facts', pattern_ids: ['context'], enabled: true }]
  };
  return api;
}

const filesystemValue: FilesystemSettings = { require_mcp_file_deletion_approval: { value: true, source: 'built_in_default' } };

type MappingsDependencies = { providerGroupMappings: ProviderGroupMappingsAdministration; groups: Pick<GroupCatalogue, 'list'> };

const builtInMappings: ProviderGroupMappings = { mappings: [], source: 'built_in_default' };

function mountSettings(api: InMemoryAgentBehaviourApi, path: string, get: FilesystemSettingsAdministration['get'] = async () => filesystemValue, mappings: MappingsDependencies = {
  providerGroupMappings: { get: async () => builtInMappings, update: async () => builtInMappings },
  groups: { list: async () => [] }
}): (nextPath: string) => void {
  const current = writable(new URL(path, origin).searchParams);
  const query = fromStore(current);
  const filesystemSettings: FilesystemSettingsAdministration = { get, update: async () => filesystemValue };
  component = mount(SystemSettingsContent, {
    target: document.body,
    props: { get query(): URLSearchParams { return query.current; }, filesystemSettings, ...mappings, diagnosticsConfiguration: api.configuration }
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
  expect(element('aside a[aria-current="location"]').textContent).toMatch(/Agent diagnostics\s*2 settings/);
  const selectedIcon = element('aside a[aria-current="location"] svg path');
  const detail = element('[aria-label="Agent diagnostics settings"]');
  expect(detail.querySelector('header h2')?.textContent).toBe('Agent diagnostics');
  expect(detail.querySelector('header svg path')?.getAttribute('d')).toBe(selectedIcon.getAttribute('d'));
  const reportingControl = element('input[aria-label="Enable diagnostic reporting"]');
  const descriptionId = reportingControl.getAttribute('aria-describedby') ?? '';
  expect(document.getElementById(descriptionId)?.textContent).toContain('Let agents submit diagnostic reports through MCP.');
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
  expect(button('Save changes').disabled).toBe(true);
  expect(findButton('Discard changes')).toBeUndefined();

  changeInstructions('Collect facts, not guesses');
  await tick();
  expect(button('Close editor').getAttribute('aria-expanded')).toBe('true');
  button('Close editor').click();
  await tick();
  expect(document.querySelector('textarea')).toBeNull();
  expect(document.body.textContent).toContain('Collect facts, not guesses');
  const save = button('Save changes');
  const reporting = element('section[aria-label="Reporting settings"]');
  expect(save.disabled).toBe(false);
  expect(reporting.compareDocumentPosition(save) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(reporting.contains(save)).toBe(false);
  expect(publish).not.toHaveBeenCalled();

  button('Discard changes').click();
  await tick();
  expect(document.body.textContent).not.toContain('Collect facts, not guesses');
  expect(button('Save changes').disabled).toBe(true);
  expect(findButton('Discard changes')).toBeUndefined();
  expect(openInstructions().value).toBe('Collect facts');
});

test('directs administrators to pattern management when reporting has not been configured', async (): Promise<void> => {
  mountSettings(new InMemoryAgentBehaviourApi(), reportingPath);
  await vi.waitFor(() => expect(document.body.textContent).toContain('No reporting settings configured.'));
  expect(element(`a[href="${patternsPath}"]`).textContent).toContain('Manage patterns');
  expect(document.querySelector('textarea')).toBeNull();
  expect(button('Save changes').disabled).toBe(true);
  expect(findButton('Discard changes')).toBeUndefined();
});

test('finishes saving from a direct Reporting settings URL while Filesystem is showing', async (): Promise<void> => {
  const api = configuredDiagnostics();
  const saved = deferred<Configuration>();
  const publish = vi.spyOn(api.configuration, 'publish').mockReturnValue(saved.promise);
  const navigate = mountSettings(api, reportingPath);
  await vi.waitFor(() => expect(document.body.textContent).toContain('Collect facts'));
  expect(element('section[aria-label="Reporting settings"]').textContent).toContain('Enable diagnostic reporting');
  expect(document.querySelector('[aria-labelledby="diagnostic-patterns-title"]')).toBeNull();
  expect(document.body.textContent).not.toContain('Add pattern');
  expect(element(`a[href="${patternsPath}"]`).textContent).toContain('Manage patterns');

  changeInstructions('Saved instructions');
  await tick();
  button('Save changes').click();
  expect(publish).toHaveBeenCalledExactlyOnceWith({
    expected_revision: api.current.revision,
    reporting_enabled: false,
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
  expect(button('Save changes').disabled).toBe(true);
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

const registeredGroup = { group_id: 'registered-team', label: 'Registered Team', description: '', revision: 1 };
const savedMappings: ProviderGroupMappings = {
  source: 'admin_override',
  mappings: [{ external_value: ' Maintainer\nTier 2 ', group_id: registeredGroup.group_id }]
};

function mappingsAdministration(initial: ProviderGroupMappings): ProviderGroupMappingsAdministration {
  let current = initial;
  return {
    get: async (): Promise<ProviderGroupMappings> => current,
    update: async (patch): Promise<ProviderGroupMappings> => {
      current = patch.operation === 'reset' ? builtInMappings : { mappings: patch.mappings, source: 'admin_override' };
      return current;
    }
  };
}

function providerValueField(): HTMLTextAreaElement {
  const fieldset = [...document.querySelectorAll('fieldset')].find((candidate): boolean => candidate.querySelector('legend')?.textContent === 'Mapping 1');
  const field = [...(fieldset?.querySelectorAll('label') ?? [])].find((label): boolean => label.textContent === 'Provider value')?.control;
  if (!(field instanceof HTMLTextAreaElement)) throw new Error('Missing provider value field');
  return field;
}

function changeProviderValue(value: string): void {
  const field = providerValueField();
  field.value = value;
  field.dispatchEvent(new Event('input', { bubbles: true }));
}

test('edits saved mappings and clears them only when the reset is saved', async (): Promise<void> => {
  const providerGroupMappings = mappingsAdministration(savedMappings);
  const get = vi.spyOn(providerGroupMappings, 'get');
  const update = vi.spyOn(providerGroupMappings, 'update');
  const navigate = mountSettings(configuredDiagnostics(), settingsPath, undefined, {
    providerGroupMappings, groups: { list: async () => [registeredGroup] }
  });
  const link = await vi.waitFor(() => element<HTMLAnchorElement>(`a[href="${mappingsPath}"]`));
  expect(get).not.toHaveBeenCalled();
  navigate(link.getAttribute('href') ?? settingsPath);

  await vi.waitFor(() => expect(providerValueField().value).toBe(' Maintainer\nTier 2 '));
  expect(link.getAttribute('aria-current')).toBe('location');
  const settings = element('section[aria-label="Group mapping settings"]');
  expect(settings.querySelector('header h2')?.textContent).toBe('Group mappings');
  expect(settings.textContent).toContain('Provider values grant group access only through saved mappings.');
  expect(settings.textContent).not.toMatch(/inherit|default/i);
  expect(button('Save changes').disabled).toBe(true);

  changeProviderValue('Edited value');
  await tick();
  button('Discard changes').click();
  await tick();
  expect(providerValueField().value).toBe(' Maintainer\nTier 2 ');
  expect(update).not.toHaveBeenCalled();

  const remove = element<HTMLButtonElement>('button[aria-label="Remove mapping 1"]');
  const mapping = providerValueField().closest('fieldset');
  expect(mapping?.contains(element<HTMLButtonElement>('button[role="combobox"]'))).toBe(true);
  expect(mapping?.contains(remove)).toBe(true);
  expect(remove.title).toBe('Remove mapping 1');
  expect(remove.textContent?.trim()).toBe('');
  expect(remove.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
  remove.click();
  await tick();
  expect(settings.textContent).toContain('No mappings.');
  button('Discard changes').click();
  await tick();
  expect(providerValueField().value).toBe(' Maintainer\nTier 2 ');

  button('Clear saved mappings').click();
  await tick();
  expect(settings.textContent).toContain('No mappings.');
  expect(settings.querySelector('textarea')).toBeNull();
  expect(update).not.toHaveBeenCalled();
  button('Discard changes').click();
  await tick();
  expect(providerValueField().value).toBe(' Maintainer\nTier 2 ');

  button('Clear saved mappings').click();
  await tick();
  button('Save changes').click();
  await vi.waitFor(() => expect(settings.textContent).toContain('No unsaved changes'));
  expect(update).toHaveBeenCalledExactlyOnceWith({ operation: 'reset' }, expect.any(AbortSignal));
  expect(settings.textContent).toContain('No mappings.');
  expect(settings.textContent).not.toContain('Clear saved mappings');
});

test('keeps rules visible after a catalogue failure and lets an unavailable group be replaced', async (): Promise<void> => {
  const stale: ProviderGroupMappings = {
    source: 'admin_override',
    mappings: [{ external_value: 'Maintainer', group_id: 'removed-team' }]
  };
  const providerGroupMappings = mappingsAdministration(stale);
  const update = vi.spyOn(providerGroupMappings, 'update');
  const list = vi.fn<GroupCatalogue['list']>()
    .mockRejectedValueOnce(new Error('Groups unavailable'))
    .mockResolvedValue([registeredGroup]);
  mountSettings(configuredDiagnostics(), mappingsPath, undefined, { providerGroupMappings, groups: { list } });

  await vi.waitFor(() => expect(document.body.textContent).toContain('Could not load registered groups.'));
  const selector = element<HTMLButtonElement>('button[role="combobox"]');
  expect(selector.textContent).toContain('removed-team');
  expect(selector.disabled).toBe(true);
  expect(providerValueField().readOnly).toBe(true);
  expect(button('Save changes').disabled).toBe(true);

  button('Retry loading groups').click();
  await vi.waitFor(() => expect(selector.textContent).toContain('removed-team (unavailable)'));
  const editedValue = ' Support\nTier 2\nEscalation ';
  changeProviderValue(editedValue);
  await tick();
  expect(button('Save changes').disabled).toBe(true);

  selector.click();
  await tick();
  const option = [...document.querySelectorAll<HTMLElement>('[role="option"]')].find((entry): boolean => entry.textContent?.trim() === 'Registered Team (registered-team)');
  if (!option) throw new Error('Missing registered group option');
  option.click();
  await tick();
  expect(selector.textContent).toContain('Registered Team (registered-team)');
  button('Save changes').click();
  await vi.waitFor(() => expect(update).toHaveBeenCalledWith({
    operation: 'set', mappings: [{ external_value: editedValue, group_id: registeredGroup.group_id }]
  }, expect.any(AbortSignal)));
  await vi.waitFor(() => expect(providerValueField().value).toBe(editedValue));
});

test('recognizes a previously unavailable target when it is registered before returning to mappings', async (): Promise<void> => {
  const list = vi.fn<GroupCatalogue['list']>().mockResolvedValueOnce([]).mockResolvedValue([registeredGroup]);
  const navigate = mountSettings(configuredDiagnostics(), mappingsPath, undefined, {
    providerGroupMappings: mappingsAdministration(savedMappings), groups: { list }
  });
  const selector = 'button[role="combobox"]';
  await vi.waitFor(() => expect(element(selector).textContent).toContain('registered-team (unavailable)'));
  navigate(settingsPath);
  await tick();
  navigate(mappingsPath);
  await vi.waitFor(() => expect(element(selector).textContent).toContain('Registered Team (registered-team)'));
  expect(list).toHaveBeenCalledTimes(2);
});

test('refreshes mappings when returning without replacing an unsaved draft', async (): Promise<void> => {
  const providerGroupMappings = mappingsAdministration(savedMappings);
  const get = vi.spyOn(providerGroupMappings, 'get');
  const navigate = mountSettings(configuredDiagnostics(), mappingsPath, undefined, {
    providerGroupMappings, groups: { list: async () => [registeredGroup] }
  });
  await vi.waitFor(() => expect(providerValueField().readOnly).toBe(false));
  changeProviderValue('unsaved provider value');
  await providerGroupMappings.update({
    operation: 'set', mappings: [{ ...savedMappings.mappings[0], external_value: 'another admin’s provider value' }]
  }, new AbortController().signal);

  navigate(settingsPath);
  await tick();
  navigate(mappingsPath);
  await vi.waitFor(() => expect(providerValueField().value).toBe('unsaved provider value'));
  expect(get).toHaveBeenCalledTimes(1);

  button('Discard changes').click();
  navigate(settingsPath);
  await tick();
  navigate(mappingsPath);
  await vi.waitFor(() => expect(providerValueField().value).toBe('another admin’s provider value'));
  expect(get).toHaveBeenCalledTimes(2);
});

test('keeps an added draft when save fails and prevents duplicate requests while pending', async (): Promise<void> => {
  const providerGroupMappings = mappingsAdministration(builtInMappings);
  const pending = Promise.withResolvers<ProviderGroupMappings>();
  const update = vi.spyOn(providerGroupMappings, 'update').mockReturnValueOnce(pending.promise);
  mountSettings(configuredDiagnostics(), mappingsPath, undefined, {
    providerGroupMappings, groups: { list: async () => [registeredGroup] }
  });
  await vi.waitFor(() => expect(button('Add mapping').disabled).toBe(false));
  const settings = element('section[aria-label="Group mapping settings"]');
  expect(settings.textContent).toContain('No mappings.');
  expect(settings.textContent).not.toContain('Clear saved mappings');
  expect(settings.querySelector('textarea')).toBeNull();

  button('Add mapping').click();
  await tick();
  expect(button('Save changes').disabled).toBe(true);
  changeProviderValue(' Level 1 Support ');
  await tick();
  const selector = element<HTMLButtonElement>('button[role="combobox"]');
  expect(selector.textContent).toContain('Select a group');
  expect(button('Save changes').disabled).toBe(true);
  expect(update).not.toHaveBeenCalled();
  selector.click();
  await tick();
  element<HTMLElement>('[role="option"]:not([aria-disabled])').click();
  await tick();

  const save = button('Save changes');
  expect(save.disabled).toBe(false);
  save.click();
  save.click();
  await tick();
  expect(save.disabled).toBe(true);
  expect(update).toHaveBeenCalledTimes(1);
  pending.reject(new HttpError(503, 'Service unavailable', null));

  await vi.waitFor(() => expect(element('[role="alert"]').textContent).toContain('Could not confirm that your changes were saved.'));
  expect(providerValueField().value).toBe(' Level 1 Support ');
  expect(save.disabled).toBe(false);
  save.click();
  await vi.waitFor(() => expect(button('Clear saved mappings').disabled).toBe(false));
  expect(update).toHaveBeenNthCalledWith(2, {
    operation: 'set', mappings: [{ external_value: ' Level 1 Support ', group_id: 'registered-team' }]
  }, expect.any(AbortSignal));
});
