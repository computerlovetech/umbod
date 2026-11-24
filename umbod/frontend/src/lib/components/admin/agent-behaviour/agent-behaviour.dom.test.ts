import { expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import { deferred, InMemoryAgentBehaviourApi, storedReport } from '#lib/agent-behaviour/in-memory.test-support.js';
import { ConfigurationState } from '#lib/agent-behaviour/state/configuration-state.svelte.js';
import { ReportsState } from '#lib/agent-behaviour/state/reports-state.svelte.js';
import ConfigurationEditor from './ConfigurationEditor.svelte';
import ReportsView from '#lib/components/shared/agent-behaviour/ReportsView.svelte';
import ReportDetailView from '#lib/components/shared/agent-behaviour/ReportDetailView.svelte';

function button(target: HTMLElement, label: string): HTMLButtonElement {
  const match = Array.from(target.querySelectorAll('button')).find((item): boolean => (item.getAttribute('aria-label') ?? item.textContent?.trim()) === label);
  expect(match).toBeDefined();
  return match!;
}

test('inspects a pattern inline and keeps its labelled actions independent of the disclosure', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi();
  api.current = { revision: 6, patterns: [{ id: 'internal-pattern', name: 'Missing context', description: 'Notice missing facts', assessment_prompt: 'Assess missing facts', inclusion_criteria: 'Required facts are missing', exclusion_criteria: 'The facts are already available', categories: ['context', 'quality'], polarity: 'negative', enabled: true }], playbooks: [{ id: 'internal-settings', name: 'Behaviour review', collection_instructions: 'Collect facts', pattern_ids: ['internal-pattern'], enabled: true, allow_proactive: false }] };
  const state = new ConfigurationState(api.configuration, vi.fn()); await state.load();
  const target = document.createElement('div'); document.body.append(target); const component = mount(ConfigurationEditor, { target, props: { state } }); flushSync();
  try {
    expect(target.textContent).toContain('Missing context');
    const reporting = target.querySelector('aside[aria-labelledby="reporting-summary-title"]');
    expect(reporting?.textContent).toContain('Saved mode: When requested');
    expect(reporting?.textContent).toContain('Umbod accepts reports only when the user asks for them.');
    expect(reporting?.textContent).not.toContain('After saving:');
    expect(target.textContent).not.toContain('internal-pattern'); expect(target.textContent).not.toContain('internal-settings');
    expect(target.textContent).not.toMatch(/revision|playbook/i);
    expect(target.querySelector('section[aria-label="Pattern editor"]')).toBeNull();
    expect(reporting?.closest('section')?.hidden).toBe(true);
    const row = target.querySelector('li');
    const pattern = row?.querySelector('details');
    expect(pattern?.open).toBe(false);
    const disclosure = pattern!.querySelector('summary')!;
    expect(disclosure.textContent?.trim()).toBe('Missing context');
    disclosure.click(); flushSync();
    expect(pattern!.open).toBe(true);
    expect(pattern!.querySelectorAll('summary')).toHaveLength(1);
    const facts = new Map(Array.from(pattern!.querySelectorAll('dt'), (term): [string, Element] => [term.textContent!.trim(), term.nextElementSibling!]));
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
    const toggle = row!.querySelector<HTMLInputElement>('label[aria-label="Enable Edited context"] input')!;
    toggle.click(); flushSync();
    expect(toggle.checked).toBe(false);
    expect(pattern!.open).toBe(true);
    button(target, 'Discard changes').click(); flushSync(); expect(target.textContent).toContain('Missing context'); expect(state.dirty).toBe(false);
    expect(reporting?.textContent).not.toContain('After saving:');
    const deleteButton = button(target, 'Delete Missing context');
    deleteButton.focus();
    deleteButton.click(); await tick();
    expect(target.textContent).toContain('No patterns configured.');
    expect(api.current.patterns).toHaveLength(1);
    const discard = button(target, 'Discard changes');
    await vi.waitFor((): void => expect(document.activeElement).toBe(discard));
    discard.click(); flushSync();
    expect(target.querySelector('li summary')?.textContent?.trim()).toBe('Missing context');
  } finally { await unmount(component); target.remove(); state.dispose(); }
});

test('shows reporting controls directly and previews the selected policy until it is saved', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi();
  api.current = { revision: 6, patterns: [{ id: 'pattern', name: 'Missing context', description: 'Notice missing facts', assessment_prompt: 'Assess missing facts', inclusion_criteria: '', exclusion_criteria: '', categories: [], polarity: 'neutral', enabled: true }], playbooks: [{ id: 'review', name: 'Behaviour review', collection_instructions: 'Collect facts', pattern_ids: ['pattern'], enabled: true, allow_proactive: false }, { id: 'secondary', name: 'Secondary review', collection_instructions: 'Collect secondary facts', pattern_ids: ['pattern'], enabled: false, allow_proactive: true }] };
  const state = new ConfigurationState(api.configuration, vi.fn());
  await state.load();
  const target = document.createElement('div'); document.body.append(target);
  const component = mount(ConfigurationEditor, { target, props: { state, section: 'reporting' } }); flushSync();
  try {
    const settings = target.querySelector<HTMLElement>('section[aria-labelledby="reporting-settings-title"]')!;
    expect(settings.hidden).toBe(false);
    expect(settings.querySelector('details')).toBeNull();
    expect(target.querySelector<HTMLElement>('section[aria-labelledby="diagnostic-patterns-title"]')?.hidden).toBe(true);
    expect(settings.querySelector('textarea')?.value).toBe('Collect facts');
    const groups = settings.querySelectorAll('fieldset');
    expect(Array.from(groups, (group): string | undefined => group.querySelector('legend')?.textContent ?? undefined)).toEqual(['Which reports Umbod accepts · Behaviour review', 'Which reports Umbod accepts · Secondary review']);
    const radios = groups[0].querySelectorAll<HTMLInputElement>('input[type="radio"]');
    expect(radios).toHaveLength(3);
    expect(radios[0].checked).toBe(true);
    radios[1].click(); flushSync();
    expect(settings.textContent).toContain('Saved mode: When requested');
    expect(settings.textContent).toContain('After saving: Automatic reports allowed');
    radios[2].click(); flushSync();
    expect(settings.textContent).toContain('After saving: Off');
    button(target, 'Save changes').click();
    await vi.waitFor((): void => expect(settings.textContent).toContain('Saved mode: Off'));
    expect(settings.textContent).not.toContain('After saving:');
    expect(api.current.playbooks[0].enabled).toBe(false);
    expect(api.current.playbooks[1]).toMatchObject({ enabled: false, allow_proactive: true, collection_instructions: 'Collect secondary facts' });
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
    expect(target.querySelector('dialog')).toBeNull();
    button(target, 'Edit New pattern').click(); flushSync();
    expect(tags()).toEqual(['tools', 'review-notes']);
    const reopenedInput = target.querySelector<HTMLInputElement>('input[name="category"]')!;
    const reopenedSave = button(target, 'Save');
    expect(reopenedSave.disabled).toBe(true);
    reopenedInput.value = 'Pending category';
    reopenedInput.dispatchEvent(new Event('input', { bubbles: true })); flushSync();
    expect(reopenedSave.disabled).toBe(false);
    reopenedSave.click(); flushSync();
    expect(target.querySelector('dialog')).toBeNull();
    button(target, 'Edit New pattern').click(); flushSync();
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
    expect(target.querySelector('dialog details')).toBeNull();
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
  const api = new InMemoryAgentBehaviourApi(); api.rows = [{ report_id: '00000000-0000-4000-8000-000000000001', received_at: '2026-06-01T00:00:00Z', expires_at: '2026-07-01T00:00:00Z', caller: { authentication: 'local_test', subject: { issuer: { value: 'issuer' }, subject: 'caller' } }, submission: { idempotency_key: '00000000-0000-4000-8000-000000000002', configuration_revision: 1, playbook_id: 'review', trigger: 'proactive', assessments: [{ pattern_id: 'first', status: 'observed', summary: 'Observed summary', evidence: ['<img src=x onerror=alert(1)>'] }, { pattern_id: 'second', status: 'not_observed', summary: '', evidence: [] }, { pattern_id: 'third', status: 'not_assessed', summary: 'Unavailable context', evidence: [] }] }, instructions: { configuration_revision: 1, playbook: { id: 'review', name: 'Original review', collection_instructions: 'Original collection instructions', pattern_ids: ['first', 'second', 'third'], enabled: true, allow_proactive: true }, patterns: ['first', 'second', 'third'].map((id) => ({ id, name: id, description: 'Original description', assessment_prompt: 'Original assessment', inclusion_criteria: 'Original inclusion', exclusion_criteria: 'Original exclusion', categories: [], polarity: 'neutral' as const, enabled: true })), reporting_guidance: 'Original guidance', resource_uri: 'umbod://agent-behaviour/playbooks/review' } }];
  const state = new ReportsState(api.reports, vi.fn());
  const target = document.createElement('div'); document.body.append(target);
  const component = mount(ReportDetailView, { target, props: { state, reportId: api.rows[0].report_id, listHref: '/insights/agent-behaviour' } });
  try {
    await vi.waitFor((): void => expect(target.querySelector('h2')?.textContent).toBe('Original review'));
    expect(target.querySelector('dialog')).toBeNull();
    expect(target.querySelector('details[open]')).toBeNull();
    expect(target.querySelector('img')).toBeNull();
    expect(target.textContent).toContain('<img src=x onerror=alert(1)>');
    expect(target.textContent).toContain('Not independently verified');
    expect(target.textContent).not.toContain('No evidence supplied');
    const links = Array.from(target.querySelectorAll('nav a'), (link): string | null => link.getAttribute('href'));
    expect(links).toEqual(['#pattern-first', '#pattern-third', '#pattern-second']);
    expect(links.map((link) => target.querySelector(`article${link}`)?.getAttribute('data-status'))).toEqual(['observed', 'not_assessed', 'not_observed']);
    expect(target.querySelector('[aria-label="Assessment summary"]')?.textContent).toContain('1 not assessed');
    expect(target.textContent).toContain('Original inclusion');
    const technical = target.querySelector('section[aria-labelledby="technical-heading"]');
    const overview = technical?.querySelector(':scope > dl');
    expect(Array.from(overview?.querySelectorAll('dt') ?? [], (label): string | null => label.textContent)).toEqual([
      'Report ID', 'Expires', 'Original configuration revision',
    ]);
    expect(overview?.textContent).toContain(api.rows[0].report_id);
    const disclosures = Array.from(technical?.querySelectorAll('details') ?? []);
    expect(disclosures.map((detail): string | null => detail.querySelector('summary')?.textContent ?? null)).toEqual([
      'Caller and authentication', 'Original collection instructions', 'Original reporting guidance',
    ]);
    expect(disclosures[0].querySelector('dl')?.textContent).toContain('caller');
    expect(disclosures[1].querySelector('p')?.textContent).toBe('Original collection instructions');
    expect(disclosures[2].querySelector('p')?.textContent).toBe('Original guidance');
  } finally { await unmount(component); target.remove(); state.dispose(); }
});
