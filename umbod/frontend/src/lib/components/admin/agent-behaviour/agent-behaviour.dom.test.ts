import { expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import { deferred, InMemoryAgentBehaviourApi, storedReport } from '#lib/agent-behaviour/in-memory.test-support.js';
import { ConfigurationState } from '#lib/agent-behaviour/state/configuration-state.svelte.js';
import { ReportsState } from '#lib/agent-behaviour/state/reports-state.svelte.js';
import ConfigurationEditor from './ConfigurationEditor.svelte';
import ReportsView from '#lib/components/shared/agent-behaviour/ReportsView.svelte';
import ReportDetailView from '#lib/components/shared/agent-behaviour/ReportDetailView.svelte';

function findButton(target: HTMLElement, label: string): HTMLButtonElement | undefined {
  return Array.from(target.querySelectorAll('button')).find((item): boolean => (item.getAttribute('aria-label') ?? item.textContent?.trim()) === label);
}

function button(target: HTMLElement, label: string): HTMLButtonElement {
  const match = findButton(target, label);
  expect(match).toBeDefined();
  return match!;
}

test('inspects a pattern inline and keeps its labelled actions independent of the disclosure', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi();
  api.current = { revision: 6, reporting_enabled: false, patterns: [{ id: 'internal-pattern', name: 'Missing context', description: 'Notice missing facts', assessment_prompt: 'Assess missing facts', inclusion_criteria: 'Required facts are missing', exclusion_criteria: 'The facts are already available', categories: ['context', 'quality'], polarity: 'negative', enabled: true }], playbooks: [{ id: 'internal-settings', name: 'Behaviour review', collection_instructions: 'Collect facts', pattern_ids: ['internal-pattern'], enabled: true }] };
  const state = new ConfigurationState(api.configuration, vi.fn()); await state.load();
  const target = document.createElement('div'); document.body.append(target); const component = mount(ConfigurationEditor, { target, props: { state } }); flushSync();
  try {
    expect(target.textContent).toContain('Missing context');
    expect(target.querySelector('section[aria-label="Reporting settings"]')).toBeNull();
    expect(target.textContent).not.toContain('internal-pattern'); expect(target.textContent).not.toContain('internal-settings');
    expect(target.textContent).not.toMatch(/revision|playbook/i);
    expect(target.querySelector('section[aria-label="Pattern editor"]')).toBeNull();
    const list = target.querySelector('[role="list"][aria-label="Patterns"]');
    expect(list?.parentElement?.textContent).toContain('Enabled');
    expect(list?.parentElement?.textContent).toContain('Actions');
    const row = list?.querySelector('li');
    const originalToggle = row?.querySelector<HTMLInputElement>('input[aria-label="Enable Missing context"]');
    expect(originalToggle?.checked).toBe(true);
    expect(findButton(target, 'Save changes')).toBeUndefined();
    expect(findButton(target, 'Discard changes')).toBeUndefined();
    originalToggle!.click(); flushSync();
    expect(button(target, 'Save changes').disabled).toBe(false);
    expect(button(target, 'Discard changes').disabled).toBe(false);
    originalToggle!.click(); flushSync();
    expect(findButton(target, 'Save changes')).toBeUndefined();
    expect(findButton(target, 'Discard changes')).toBeUndefined();
    const disclosure = button(row!, 'Missing context');
    const pattern = document.getElementById(disclosure.getAttribute('aria-controls') ?? '');
    if (!pattern) throw new Error('Pattern disclosure panel is missing');
    expect(disclosure.getAttribute('aria-expanded')).toBe('false');
    expect(pattern.hidden).toBe(true);
    expect(pattern.textContent).toContain('Notice missing facts');
    disclosure.click(); flushSync();
    expect(disclosure.getAttribute('aria-expanded')).toBe('true');
    expect(pattern.hidden).toBe(false);
    expect(row!.querySelectorAll('button[aria-expanded]')).toHaveLength(1);
    const facts = new Map(Array.from(pattern.querySelectorAll('dt'), (term): [string, Element] => [term.textContent!.trim(), term.nextElementSibling!]));
    expect(facts.get('When it counts')?.textContent).toBe('Required facts are missing');
    expect(facts.get('When it does not count')?.textContent).toBe('The facts are already available');
    expect(facts.get('Assessment prompt')?.textContent).toBe('Assess missing facts');
    expect(Array.from(facts.get('Categories')!.children, (badge): string | null => badge.textContent)).toEqual(['context', 'quality']);
    expect(facts.get('Polarity')?.firstElementChild?.textContent).toBe('negative');
    button(target, 'Edit Missing context').click(); flushSync();
    expect(target.querySelector('dialog[aria-labelledby="pattern-editor-title"]')).not.toBeNull();
    expect(target.textContent).toContain('What should the agent notice?'); expect(target.textContent).toContain('When it counts'); expect(target.textContent).toContain('When it does not count');
    const name = target.querySelector<HTMLInputElement>('dialog #pattern-name')!;
    const save = button(target, 'Save');
    expect(save.disabled).toBe(true);
    function enterName(value: string): void {
      name.value = value; name.dispatchEvent(new Event('input', { bubbles: true })); flushSync();
    }
    enterName('Edited context');
    expect(save.disabled).toBe(false);
    enterName('Missing context');
    expect(save.disabled).toBe(true);
    enterName('Edited context');
    expect(target.textContent).toContain('Unsaved changes');
    save.click(); flushSync();
    const toggle = row!.querySelector<HTMLInputElement>('input[type="checkbox"][aria-label="Enable Edited context"]')!;
    toggle.click(); flushSync();
    expect(toggle.checked).toBe(false);
    expect(disclosure.getAttribute('aria-expanded')).toBe('true');
    expect(pattern.hidden).toBe(false);
    button(target, 'Discard changes').click(); flushSync(); expect(target.textContent).toContain('Missing context'); expect(state.dirty).toBe(false);
    const deleteButton = button(target, 'Delete Missing context');
    deleteButton.focus();
    deleteButton.click(); await tick();
    expect(target.textContent).toContain('No patterns configured.');
    expect(api.current.patterns).toHaveLength(1);
    const discard = button(target, 'Discard changes');
    await vi.waitFor((): void => expect(document.activeElement).toBe(discard));
    discard.click(); flushSync();
    expect(target.querySelector('li button[aria-expanded="false"]')?.textContent?.trim()).toBe('Missing context');
    expect(findButton(target, 'Save changes')).toBeUndefined();
    expect(findButton(target, 'Discard changes')).toBeUndefined();
  } finally { await unmount(component); target.remove(); state.dispose(); }
});

function reportingFixture(): InMemoryAgentBehaviourApi {
  const api = new InMemoryAgentBehaviourApi();
  api.current = { revision: 6, reporting_enabled: true, patterns: [{ id: 'pattern', name: 'Missing context', description: 'Notice missing facts', assessment_prompt: 'Assess missing facts', inclusion_criteria: '', exclusion_criteria: '', categories: [], polarity: 'neutral', enabled: true }], playbooks: [{ id: 'review', name: 'Behaviour review', collection_instructions: 'Collect facts', pattern_ids: ['pattern'], enabled: true }, { id: 'secondary', name: 'Secondary review', collection_instructions: 'Collect secondary facts', pattern_ids: ['pattern'], enabled: false }] };
  return api;
}

test.each(['Missing context', 'Neighbor pattern'] as const)('deleting %s focuses the remaining pattern disclosure', async (name): Promise<void> => {
  const api = reportingFixture();
  api.current.patterns.push({ ...api.current.patterns[0], id: 'neighbor', name: 'Neighbor pattern' });
  const state = new ConfigurationState(api.configuration, vi.fn());
  await state.load();
  const target = document.createElement('div');
  document.body.append(target);
  const component = mount(ConfigurationEditor, { target, props: { state } });
  try {
    const neighbor = button(target, name === 'Missing context' ? 'Neighbor pattern' : 'Missing context');
    const remove = button(target, `Delete ${name}`);
    remove.focus();
    remove.click();
    await vi.waitFor((): void => expect(document.activeElement).toBe(neighbor));
    expect(neighbor.getAttribute('aria-expanded')).toBe('false');
  } finally { await unmount(component); target.remove(); state.dispose(); }
});

test('uses one reporting switch and preserves collection instructions and memberships when turned off and on', async (): Promise<void> => {
  const api = reportingFixture();
  const { patterns, playbooks } = structuredClone(api.current);
  const state = new ConfigurationState(api.configuration, vi.fn());
  await state.load();
  const target = document.createElement('div'); document.body.append(target);
  const component = mount(ConfigurationEditor, { target, props: { state, section: 'reporting' } }); flushSync();
  try {
    const settings = target.querySelector<HTMLElement>('section[aria-label="Reporting settings"]')!;
    const toggle = reportingToggle(settings);
    expect(settings.querySelectorAll('input[type="checkbox"]')).toHaveLength(1);
    expect(settings.querySelector('select, [role="combobox"]')).toBeNull();
    button(target, 'Exclude playbook · Behaviour review').click(); flushSync();
    expect(settings.textContent).toContain('No usable playbook');
    button(target, 'Include playbook · Behaviour review').click(); flushSync();
    expect(settings.textContent).not.toContain('No usable playbook');
    expect(findButton(target, 'Include playbook · Secondary review')).toBeDefined();
    expect(toggle.checked).toBe(true);
    expect(settings.textContent).toContain('Saved: On');
    expect(settings.textContent).not.toContain('Draft:');

    toggle.click(); flushSync();
    expect(settings.textContent).toContain('Saved: On');
    expect(settings.textContent).toContain('Draft: Off');
    button(target, 'Discard changes').click(); flushSync();
    expect(toggle.checked).toBe(true);
    expect(settings.textContent).not.toContain('Draft:');

    toggle.click(); flushSync();
    button(target, 'Save changes').click();
    await vi.waitFor((): void => expect(settings.textContent).toContain('Saved: Off'));
    expect(api.current.reporting_enabled).toBe(false);
    expect(api.current.patterns).toEqual(patterns);
    expect(api.current.playbooks).toEqual(playbooks);

    button(target, 'Edit instructions · Secondary review').click(); flushSync();
    const instructions = settings.querySelector<HTMLTextAreaElement>('textarea')!;
    expect(instructions.value).toBe('Collect secondary facts');
    expect(instructions.disabled).toBe(false);
    instructions.value = 'Collect updated facts';
    instructions.dispatchEvent(new Event('input', { bubbles: true })); flushSync();
    button(target, 'Save changes').click();
    await vi.waitFor((): void => expect(findButton(target, 'Discard changes')).toBeUndefined());
    expect(api.current.playbooks[1].collection_instructions).toBe('Collect updated facts');
    expect(toggle.checked).toBe(false);
    toggle.click(); flushSync();
    expect(settings.textContent).toContain('Draft: On');
    button(target, 'Save changes').click();
    await vi.waitFor((): void => expect(settings.textContent).toContain('Saved: On'));
    expect(settings.textContent).not.toContain('Draft:');
    expect(api.current.reporting_enabled).toBe(true);
    expect(api.current.patterns).toEqual(patterns);
    expect(api.current.playbooks).toEqual([playbooks[0], { ...playbooks[1], collection_instructions: 'Collect updated facts' }]);
  } finally { await unmount(component); target.remove(); state.dispose(); }
});

function reportingToggle(target: HTMLElement): HTMLInputElement {
  const toggle = target.querySelector<HTMLInputElement>('input[aria-label="Enable diagnostic reporting"]');
  if (!toggle) throw new Error('Missing diagnostic reporting switch');
  return toggle;
}

test('recovers a single excluded playbook without enabling it when the global switch changes', async (): Promise<void> => {
  const api = reportingFixture();
  api.current.reporting_enabled = false;
  api.current.playbooks = [{ ...api.current.playbooks[0], enabled: false }];
  const state = new ConfigurationState(api.configuration);
  await state.load();
  const target = document.createElement('div'); document.body.append(target);
  const component = mount(ConfigurationEditor, { target, props: { state, section: 'reporting' } }); flushSync();
  try {
    const toggle = reportingToggle(target);
    expect(target.querySelectorAll('input[type="checkbox"]')).toHaveLength(1);
    expect(toggle.checked).toBe(false);
    const include = button(target, 'Include playbook');
    expect(include.disabled).toBe(false);
    toggle.click(); flushSync();
    expect(target.textContent).toContain('No usable playbook');
    expect(button(target, 'Include playbook')).toBe(include);
    include.focus();
    include.click();
    await tick();
    expect(target.textContent).not.toContain('No usable playbook');
    expect(findButton(target, 'Include playbook')).toBeUndefined();
    expect(findButton(target, 'Exclude playbook')).toBeUndefined();
    await vi.waitFor((): void => expect(document.activeElement).toBe(button(target, 'Edit instructions')));
    button(target, 'Save changes').click();
    await vi.waitFor((): void => expect(target.textContent).toContain('Saved: On'));
    expect(api.current.playbooks[0]).toMatchObject({ enabled: true, pattern_ids: ['pattern'], collection_instructions: 'Collect facts' });
  } finally { await unmount(component); target.remove(); state.dispose(); }
});

test('keeps the saved unavailability visible until a usable playbook is published', async (): Promise<void> => {
  const api = reportingFixture();
  api.current.playbooks = [{ ...api.current.playbooks[0], enabled: false }];
  const state = new ConfigurationState(api.configuration);
  await state.load();
  const target = document.createElement('div'); document.body.append(target);
  const component = mount(ConfigurationEditor, { target, props: { state, section: 'reporting' } }); flushSync();
  try {
    expect(target.textContent).toContain('No usable playbook in the saved configuration.');
    button(target, 'Include playbook').click(); await tick();
    expect(target.textContent).toContain('No usable playbook in the saved configuration.');
    button(target, 'Save changes').click();
    await vi.waitFor((): void => expect(target.textContent).not.toContain('No usable playbook'));
  } finally { await unmount(component); target.remove(); state.dispose(); }
});

test('warns of missing usable playbooks when the draft enables reporting', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi();
  const state = new ConfigurationState(api.configuration, vi.fn());
  await state.load();
  const target = document.createElement('div'); document.body.append(target);
  const component = mount(ConfigurationEditor, { target, props: { state, section: 'reporting' } }); flushSync();
  try {
    const toggle = reportingToggle(target);
    expect(toggle.checked).toBe(false);
    expect(target.textContent).not.toContain('No usable playbook');
    toggle.click(); flushSync();
    expect(target.textContent).toContain('No usable playbook');
    expect(button(target, 'Save changes').disabled).toBe(false);
    button(target, 'Discard changes').click(); flushSync();
    expect(target.textContent).not.toContain('No usable playbook');
  } finally { await unmount(component); target.remove(); state.dispose(); }
});

test('keeps the reporting draft separate from the saved setting when publishing conflicts', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi();
  const state = new ConfigurationState(api.configuration, vi.fn());
  const loading = deferred<typeof api.current>();
  const get = vi.spyOn(api.configuration, 'get').mockReturnValueOnce(loading.promise);
  const loaded = state.load();
  const target = document.createElement('div'); document.body.append(target);
  const component = mount(ConfigurationEditor, { target, props: { state, section: 'reporting' } }); flushSync();
  try {
    expect(target.querySelector('input')).toBeNull();
    expect(target.textContent).not.toContain('Saved:');
    expect(button(target, 'Loading…').disabled).toBe(true);
    loading.resolve({ ...api.current, reporting_enabled: true });
    await loaded; flushSync();
    const toggle = reportingToggle(target);
    expect(toggle.checked).toBe(true);
    toggle.click(); flushSync();
    api.current = { ...api.current, revision: 1, reporting_enabled: true };
    button(target, 'Save changes').click();
    await vi.waitFor((): void => expect(target.textContent).toContain('Another administrator saved changes.'));
    expect(toggle.checked).toBe(false);
    expect(target.textContent).toContain('Saved: On');
    expect(target.textContent).toContain('Draft: Off');
    expect(button(target, 'Save changes').disabled).toBe(true);
    button(target, 'Discard changes').click(); flushSync();
    expect(toggle.checked).toBe(true);
    expect(target.textContent).not.toContain('Draft:');
  } finally { await unmount(component); target.remove(); state.dispose(); get.mockRestore(); }
});

test.each(['Close', 'Escape'])('dismisses an unsaved new pattern with %s without changing the list', async (dismissal): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi();
  const state = new ConfigurationState(api.configuration, vi.fn(), (): string => 'new-pattern');
  await state.load();
  const target = document.createElement('div'); document.body.append(target);
  const component = mount(ConfigurationEditor, { target, props: { state } }); flushSync();
  try {
    button(target, 'Add pattern').click(); flushSync();
    const dialog = target.querySelector('dialog')!;
    expect(dialog.querySelector('h2')?.textContent).toBe('New pattern');
    expect(target.textContent).toContain('0 of 0 enabled');
    const name = dialog.querySelector<HTMLInputElement>('#pattern-name')!;
    name.value = 'Abandoned pattern'; name.dispatchEvent(new Event('input', { bubbles: true })); flushSync();
    expect(dialog.querySelector('h2')?.textContent).toBe('New pattern');
    expect(target.querySelector('#diagnostic-patterns-title')?.closest('section')?.querySelector('li button[aria-expanded]')).toBeNull();
    expect(target.textContent).not.toContain('Unsaved changes');
    if (dismissal === 'Close') button(dialog, 'Close').click();
    else dialog.dispatchEvent(new Event('cancel', { cancelable: true }));
    flushSync();
    expect(target.querySelector('dialog')).toBeNull();
    expect(target.textContent).toContain('No patterns configured.');
    expect(findButton(target, 'Save changes')).toBeUndefined();
    button(target, 'Add pattern').click(); flushSync();
    expect(target.querySelector<HTMLInputElement>('dialog #pattern-name')?.value).toBe('');
  } finally { await unmount(component); target.remove(); state.dispose(); }
});

test('adds and removes category tags without publishing the pattern', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi();
  const state = new ConfigurationState(api.configuration, vi.fn(), (): string => 'new-pattern');
  await state.load(); await state.addPattern();
  const target = document.createElement('div'); document.body.append(target);
  const component = mount(ConfigurationEditor, { target, props: { state } }); flushSync();
  try {
    const input = target.querySelector<HTMLInputElement>('input[name="category"]')!;
    const add = button(target, 'Add category');
    const save = button(target, 'Save');
    function enterTag(value: string): void {
      input.value = value;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      flushSync();
    }
    function submitTag(value: string): void {
      enterTag(value);
      add.click(); flushSync();
    }
    expect(save.disabled).toBe(true);
    enterTag('Missing Context');
    expect(save.disabled).toBe(false);
    enterTag('');
    expect(save.disabled).toBe(true);
    submitTag('Missing Context');
    const tags = (): (string | null)[] => Array.from(target.querySelectorAll('[aria-label="Added categories"] li'), (item): string | null => item.textContent?.trim() ?? null);
    expect(tags()).toEqual(['missing-context']);
    expect(input.value).toBe('');
    submitTag('missing-context');
    expect(input.validationMessage).toBe('This category is already added.');
    expect(tags()).toEqual(['missing-context']);
    submitTag('tools');
    expect(tags()).toEqual(['missing-context', 'tools']);
    button(target, 'Remove category missing-context').click(); flushSync();
    expect(tags()).toEqual(['tools']);
    expect(document.activeElement).toBe(input);
    enterTag('tools');
    save.click(); flushSync();
    expect(input.validationMessage).toBe('This category is already added.');
    expect(input.isConnected).toBe(true);
    enterTag('Review notes');
    save.click(); flushSync();
    expect(target.querySelector('dialog [role="status"]')?.textContent).toContain('Add a name');
    expect(target.querySelector('#diagnostic-patterns-title')?.closest('section')?.querySelector('li button[aria-expanded]')).toBeNull();
    for (const [selector, value] of [['#pattern-name', 'Tool context'], ['#pattern-description', 'Notice missing tool context']]) {
      const field = target.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector);
      expect(field).not.toBeNull();
      field!.value = value;
      field!.dispatchEvent(new Event('input', { bubbles: true }));
    }
    flushSync();
    save.click();
    await vi.waitFor((): void => expect(target.querySelector('dialog')).toBeNull());
    expect(target.querySelector('li button[aria-expanded="false"]')?.textContent?.trim()).toBe('Tool context');
    expect(button(target, 'Save changes').disabled).toBe(false);
    button(target, 'Edit Tool context').click(); flushSync();
    expect(tags()).toEqual(['tools', 'review-notes']);
    const reopenedInput = target.querySelector<HTMLInputElement>('input[name="category"]')!;
    const reopenedSave = button(target, 'Save');
    expect(reopenedSave.disabled).toBe(true);
    reopenedInput.value = 'Pending category';
    reopenedInput.dispatchEvent(new Event('input', { bubbles: true })); flushSync();
    expect(reopenedSave.disabled).toBe(false);
    reopenedSave.click(); flushSync();
    expect(target.querySelector('dialog')).toBeNull();
    button(target, 'Edit Tool context').click(); flushSync();
    expect(tags()).toEqual(['tools', 'review-notes', 'pending-category']);
    expect(api.current.patterns).toHaveLength(0);
  } finally { await unmount(component); target.remove(); state.dispose(); }
});

test('uses labelled shared dropdowns to draft filters before explicitly running the query', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi();
  const list = vi.spyOn(api.reports, 'list');
  const state = new ReportsState(api.reports, vi.fn(), () => ({ patterns: [{ id: 'current-pattern', name: 'Current pattern name' }], playbooks: [{ id: 'current-settings', name: 'Current reporting name' }] }));
  await state.load();
  const target = document.createElement('div'); document.body.append(target);
  const component = mount(ReportsView, { target, props: { state, listHref: '/insights/agent-behaviour' } }); flushSync();
  try {
    expect(target.querySelector('select')).toBeNull();
    const controls = target.querySelectorAll<HTMLButtonElement>('[role="combobox"]');
    expect(controls).toHaveLength(3);
    for (const [index, key, label, value, choices] of [
      [0, 'playbook_id', 'Reporting settings', 'current-settings', ['All reporting settings', 'Current reporting name']],
      [1, 'pattern_id', 'Pattern', 'current-pattern', ['All patterns', 'Current pattern name']],
      [2, 'status', 'Status', 'observed', ['All statuses', 'Observed', 'Not observed', 'Not assessed']]
    ] as const) {
      state.paginate(1);
      await vi.waitFor((): void => expect(state.busy).toBe(false));
      expect(state.query.offset).toBe(25);
      const control = controls[index];
      expect(target.querySelector(`label[for="${control.id}"]`)?.textContent).toBe(label);
      control.click(); flushSync();
      const listbox = document.getElementById(control.getAttribute('aria-controls')!)!;
      expect(listbox.getAttribute('role')).toBe('listbox');
      expect(listbox.getAttribute('aria-label')).toBe(label);
      const options = listbox.querySelectorAll<HTMLElement>('[role="option"]');
      expect(Array.from(options, (option): string | null | undefined => option.querySelector('span')?.textContent)).toEqual(choices);
      options[1].click(); await tick(); flushSync();
      await vi.waitFor((): void => expect(control.getAttribute('aria-expanded')).toBe('false'));
      expect(control.textContent).toContain(choices[1]);
      expect(state.draftQuery[key]).toBe(value);
      expect(state.query.offset).toBe(25);
      const callsBeforeRun = list.mock.calls.length;
      const form = target.querySelector('form');
      expect(form).not.toBeNull();
      form!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
      await vi.waitFor((): void => expect(list).toHaveBeenCalledTimes(callsBeforeRun + 1));
      expect(state.query[key]).toBe(value);
      expect(state.query.offset).toBe(0);
      expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ [key]: value, offset: 0 }), expect.anything());
      control.click(); flushSync();
      document.getElementById(control.getAttribute('aria-controls')!)!.querySelector<HTMLElement>('[role="option"]')!.click();
      await tick(); flushSync();
      expect(control.textContent).toContain(choices[0]);
      expect(state.draftQuery[key]).toBeUndefined();
      expect(state.query[key]).toBe(value);
      expect(state.query.offset).toBe(0);
    }
  } finally { await unmount(component); target.remove(); state.dispose(); list.mockRestore(); }
});

test('edits pattern polarity through the shared dropdown inside the pattern dialog', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi();
  const state = new ConfigurationState(api.configuration, vi.fn(), (): string => 'new-pattern');
  await state.load(); await state.addPattern();
  const target = document.createElement('div'); document.body.append(target);
  const component = mount(ConfigurationEditor, { target, props: { state } }); flushSync();
  try {
    expect(target.querySelector('dialog :is(details, button[aria-expanded]:not([role="combobox"]))')).toBeNull();
    expect(target.querySelector('select')).toBeNull();
    const control = target.querySelector<HTMLButtonElement>('[role="combobox"]')!;
    expect(target.querySelector(`label[for="${control.id}"]`)?.textContent).toBe('Polarity');
    control.click(); flushSync();
    const listbox = document.getElementById(control.getAttribute('aria-controls')!)!;
    expect(listbox.closest('dialog')).toBe(target.querySelector('dialog'));
    const positive = Array.from(listbox.querySelectorAll<HTMLElement>('[role="option"]')).find((option): boolean => option.textContent === 'Positive');
    expect(positive).toBeDefined();
    positive!.click(); await tick(); flushSync();
    expect(state.selected?.polarity).toBe('positive');
    expect(control.textContent).toContain('Positive');
    expect(control.getAttribute('aria-expanded')).toBe('false');
    expect(api.current.patterns).toHaveLength(0);
  } finally { await unmount(component); target.remove(); state.dispose(); }
});

test('focuses a linked pattern once the report arrives', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi();
  const report = storedReport();
  const pending = deferred<typeof report>();
  const state = new ReportsState({ list: api.reports.list, get: () => pending.promise }, vi.fn());
  const originalUrl = window.location.href;
  window.history.replaceState(null, '', '#pattern-fallback');
  const target = document.createElement('div'); document.body.append(target);
  const component = mount(ReportDetailView, { target, props: { state, reportId: report.report_id, listHref: '/insights/agent-behaviour' } });
  try {
    expect(target.querySelector('#pattern-fallback')).toBeNull();
    pending.resolve(report);
    await vi.waitFor((): void => expect(document.activeElement?.id).toBe('pattern-fallback'));
  } finally {
    await unmount(component);
    target.remove();
    state.dispose();
    window.history.replaceState(null, '', originalUrl);
  }
});

test('renders original report snapshots and evidence only as escaped text', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi(); api.rows = [{ report_id: '00000000-0000-4000-8000-000000000001', received_at: '2026-06-01T00:00:00Z', expires_at: '2026-07-01T00:00:00Z', caller: { authentication: 'local_test', subject: { issuer: { value: 'issuer' }, subject: 'caller' } }, submission: { idempotency_key: '00000000-0000-4000-8000-000000000002', configuration_revision: 1, playbook_id: 'review', trigger: 'proactive', assessments: [{ pattern_id: 'first', status: 'observed', summary: 'Observed summary', evidence: ['<img src=x onerror=alert(1)>'] }, { pattern_id: 'second', status: 'not_observed', summary: '', evidence: [] }, { pattern_id: 'third', status: 'not_assessed', summary: 'Unavailable context', evidence: [] }] }, instructions: { configuration_revision: 1, playbook: { id: 'review', name: 'Original review', collection_instructions: 'Original collection instructions', pattern_ids: ['first', 'second', 'third'], enabled: true }, patterns: ['first', 'second', 'third'].map((id) => ({ id, name: id, description: 'Original description', assessment_prompt: 'Original assessment', inclusion_criteria: 'Original inclusion', exclusion_criteria: 'Original exclusion', categories: [], polarity: 'neutral' as const, enabled: true })), reporting_guidance: 'Original guidance', resource_uri: 'umbod://agent-behaviour/playbooks/review' } }];
  const state = new ReportsState(api.reports, vi.fn());
  const target = document.createElement('div'); document.body.append(target);
  const component = mount(ReportDetailView, { target, props: { state, reportId: api.rows[0].report_id, listHref: '/insights/agent-behaviour' } });
  try {
    await vi.waitFor((): void => expect(target.querySelector('h2')?.textContent).toBe('Original review'));
    expect(target.querySelector('dialog')).toBeNull();
    expect(target.querySelector('img')).toBeNull();
    expect(target.textContent).toContain('<img src=x onerror=alert(1)>');
    expect(target.textContent).toContain('Not independently verified');
    expect(target.textContent).toContain('Agent-reported trigger: proactive');
    expect(target.textContent).not.toContain('No evidence supplied');
    const links = Array.from(target.querySelectorAll('nav a'), (link): string | null => link.getAttribute('href'));
    expect(links).toEqual(['#pattern-first', '#pattern-third', '#pattern-second']);
    expect(links.map((link) => target.querySelector(`article${link}`)?.getAttribute('data-status'))).toEqual(['observed', 'not_assessed', 'not_observed']);
    expect(target.querySelector('[aria-label="Assessment summary"]')?.textContent).toContain('1 not assessed');
    const technical = target.querySelector<HTMLElement>('section[aria-labelledby="technical-heading"]');
    if (!technical) throw new Error('Missing technical details');
    const overview = technical.querySelector(':scope > dl');
    expect(Array.from(overview?.querySelectorAll('dt') ?? [], (label): string | null => label.textContent)).toEqual([
      'Report ID', 'Expires', 'Original configuration revision',
    ]);
    expect(overview?.textContent).toContain(api.rows[0].report_id);
    const disclosures = Array.from(target.querySelectorAll<HTMLButtonElement>('button[aria-controls]'));
    expect(disclosures.map((trigger): string | undefined => trigger.textContent?.trim())).toEqual([
      'View original criteria', 'View original criteria', 'View original criteria',
      'Caller and authentication', 'Original collection instructions', 'Original reporting guidance',
    ]);
    const panels = disclosures.map((trigger): HTMLElement => {
      const id = trigger.getAttribute('aria-controls');
      const panel = id && document.getElementById(id);
      if (!panel) throw new Error('Missing disclosure panel');
      expect(trigger.getAttribute('aria-expanded')).toBe('false');
      expect(panel.hidden).toBe(true);
      return panel;
    });
    expect(new Set(panels).size).toBe(disclosures.length);
    const originalContent = [
      'Original inclusion', 'Original inclusion', 'Original inclusion',
      'caller', 'Original collection instructions', 'Original guidance',
    ];
    for (const [index, trigger] of disclosures.entries()) {
      trigger.click(); flushSync();
      expect(trigger.getAttribute('aria-expanded')).toBe('true');
      expect(panels[index].textContent).toContain(originalContent[index]);
      expect(panels.filter((panel): boolean => !panel.hidden)).toEqual([panels[index]]);
      trigger.click(); flushSync();
      expect(trigger.getAttribute('aria-expanded')).toBe('false');
      expect(panels[index].hidden).toBe(true);
    }
  } finally { await unmount(component); target.remove(); state.dispose(); }
});
