import { expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import { InMemoryAgentBehaviourApi } from '#lib/agent-behaviour/in-memory.test-support.js';
import { ConfigurationState } from '#lib/agent-behaviour/state/configuration-state.svelte.js';
import { ReportsState } from '#lib/agent-behaviour/state/reports-state.svelte.js';
import ConfigurationEditor from './ConfigurationEditor.svelte';
import ReportsView from './ReportsView.svelte';

function button(target: HTMLElement, label: string): HTMLButtonElement {
  const match = Array.from(target.querySelectorAll('button')).find((item): boolean => item.textContent?.trim() === label);
  expect(match).toBeDefined();
  return match!;
}

test('shows pattern cards first, hides settings and edits through plain labelled controls', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi();
  api.current = { revision: 6, patterns: [{ id: 'internal-pattern', name: 'Missing context', description: 'Notice missing facts', assessment_prompt: 'Assess missing facts', inclusion_criteria: '', exclusion_criteria: '', categories: [], polarity: 'neutral', enabled: true }], playbooks: [{ id: 'internal-settings', name: 'Behaviour review', collection_instructions: 'Collect facts', pattern_ids: ['internal-pattern'], enabled: true, allow_proactive: false }] };
  const state = new ConfigurationState(api.configuration, vi.fn()); await state.load();
  const target = document.createElement('div'); document.body.append(target); const component = mount(ConfigurationEditor, { target, props: { state } }); flushSync();
  try {
    expect(target.textContent).toContain('Missing context');
    expect(target.textContent).toContain('Reporting · When requested');
    expect(target.textContent).not.toContain('internal-pattern'); expect(target.textContent).not.toContain('internal-settings');
    expect(target.textContent).not.toMatch(/revision|playbook/i);
    expect(target.querySelector('section[aria-label="Pattern editor"]')).toBeNull();
    const settings = Array.from(target.querySelectorAll('details')).find((item): boolean => item.querySelector('summary')?.textContent === 'Reporting settings')!;
    expect(settings.open).toBe(false);
    expect(settings.textContent).toContain('Allow agents to report without being asked');
    const consent = settings.querySelector<HTMLInputElement>('label[aria-label="Allow agents to report without being asked"] input')!;
    expect(consent.checked).toBe(false);
    settings.querySelector('summary')!.click(); flushSync(); expect(settings.open).toBe(true);
    consent.click(); flushSync(); expect(state.settings[0].allow_proactive).toBe(true);
    button(target, 'Edit').click(); flushSync();
    expect(target.querySelector('dialog[aria-labelledby="pattern-editor-title"]')).not.toBeNull();
    expect(target.textContent).toContain('What should the agent notice?'); expect(target.textContent).toContain('When it counts'); expect(target.textContent).toContain('When it does not count');
    const name = target.querySelector<HTMLInputElement>('section input')!;
    name.value = 'Edited context'; name.dispatchEvent(new Event('input', { bubbles: true })); flushSync();
    expect(target.textContent).toContain('Unsaved changes');
    button(target, 'Done editing').click(); flushSync();
    const toggle = target.querySelector<HTMLInputElement>('article input[type="checkbox"]')!;
    toggle.click(); flushSync(); expect(state.patterns[0].enabled).toBe(false);
    button(target, 'Discard changes').click(); flushSync(); expect(target.textContent).toContain('Missing context'); expect(state.dirty).toBe(false);
    button(target, 'Remove').click(); flushSync(); expect(target.textContent).toContain('No patterns configured.');
  } finally { await unmount(component); target.remove(); state.dispose(); }
});

test('uses labelled shared dropdowns to draft filters before explicitly running the query', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi();
  const list = vi.spyOn(api.reports, 'list');
  const state = new ReportsState(api.reports, vi.fn(), () => ({ patterns: [{ id: 'current-pattern', name: 'Current pattern name' }], playbooks: [{ id: 'current-settings', name: 'Current reporting name' }] }));
  await state.load();
  const target = document.createElement('div'); document.body.append(target);
  const component = mount(ReportsView, { target, props: { state } }); flushSync();
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
    target.querySelector<HTMLElement>('section details summary')!.click(); flushSync();
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

test('renders original report snapshots and evidence only as escaped text', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi(); api.rows = [{ report_id: '00000000-0000-4000-8000-000000000001', received_at: '2026-06-01T00:00:00Z', expires_at: '2026-07-01T00:00:00Z', caller: { authentication: 'local_test', subject: { issuer: { value: 'issuer' }, subject: 'caller' } }, submission: { idempotency_key: '00000000-0000-4000-8000-000000000002', configuration_revision: 1, playbook_id: 'review', trigger: 'proactive', assessments: [{ pattern_id: 'first', status: 'observed', summary: 'Observed summary', evidence: ['<img src=x onerror=alert(1)>'] }, { pattern_id: 'second', status: 'not_observed', summary: '', evidence: [] }, { pattern_id: 'third', status: 'not_assessed', summary: 'Unavailable context', evidence: [] }] }, instructions: { configuration_revision: 1, playbook: { id: 'review', name: 'Original review', collection_instructions: 'Original collection instructions', pattern_ids: ['first', 'second', 'third'], enabled: true, allow_proactive: true }, patterns: ['first', 'second', 'third'].map((id) => ({ id, name: id, description: 'Original description', assessment_prompt: 'Original assessment', inclusion_criteria: 'Original inclusion', exclusion_criteria: 'Original exclusion', categories: [], polarity: 'neutral' as const, enabled: true })), reporting_guidance: 'Original guidance', resource_uri: 'umbod://agent-behaviour/playbooks/review' } }];
  const state = new ReportsState(api.reports, vi.fn(), () => ({ patterns: [{ id: 'current-pattern', name: 'Current pattern name' }], playbooks: [{ id: 'current-settings', name: 'Current reporting name' }] })); await state.load();
  const target = document.createElement('div'); document.body.append(target); const component = mount(ReportsView, { target, props: { state } }); flushSync();
  await vi.waitFor((): void => expect(state.busy).toBe(false)); flushSync();
  expect(target.querySelectorAll('.insight-query-fields [role="combobox"]')).toHaveLength(3);
  expect(target.textContent).toContain('Previous reporting settings'); expect(target.textContent).toContain('Removed pattern');
  expect(target.textContent).not.toContain('Revision'); expect(target.textContent).not.toContain(api.rows[0].report_id);
  target.querySelector<HTMLButtonElement>('.report-row')!.click(); await vi.waitFor((): void => expect(state.detail).not.toBeNull()); flushSync();
  expect(target.querySelector('.detail details:last-of-type')?.hasAttribute('open')).toBe(false);
  expect(target.querySelector('img')).toBeNull(); expect(target.textContent).toContain('<img src=x onerror=alert(1)>'); expect(target.textContent).toContain('Not independently verified');
  expect(Array.from(target.querySelectorAll('[data-status]')).map((node): string | null => node.textContent)).toEqual(['Observed', 'Not observed', 'Not assessed']); expect(target.textContent).toContain('Original inclusion'); expect(target.textContent).toContain('Original collection instructions'); expect(target.textContent).toContain('caller');
  await unmount(component); target.remove(); state.dispose();
});
