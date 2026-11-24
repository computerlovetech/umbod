import { flushSync, mount, unmount } from 'svelte';
import { expect, test, vi } from 'vitest';
import { HttpError } from '#lib/admin/infrastructure/transport.js';
import { InMemoryAgentBehaviourApi, storedReport } from '#lib/agent-behaviour/in-memory.test-support.js';
import { PersonalReportsState } from '#lib/agent-behaviour/state/personal-reports-state.svelte.js';
import PersonalAgentBehaviourView from './PersonalAgentBehaviourView.svelte';

function choose(target: HTMLElement, label: string, choice: string): void {
  const controlLabel = Array.from(target.querySelectorAll('label')).find((item): boolean => item.textContent === label);
  expect(controlLabel).toBeDefined();
  const control = document.getElementById(controlLabel!.htmlFor)!;
  control.click(); flushSync();
  const listbox = document.getElementById(control.getAttribute('aria-controls')!)!;
  const option = Array.from(listbox.querySelectorAll<HTMLElement>('[role="option"]')).find((item): boolean => item.textContent?.trim() === choice);
  expect(option).toBeDefined();
  option!.click(); flushSync();
}

test('uses owned report snapshots to filter and inspect entries without admin controls', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi();
  api.rows = [storedReport()];
  const list = vi.fn(api.reports.list);
  const state = new PersonalReportsState({ list, get: api.reports.get });
  const target = document.createElement('div'); document.body.append(target);
  let component = mount(PersonalAgentBehaviourView, { target, props: { state } });
  try {
    await vi.waitFor((): void => expect(target.querySelector('.report-row')?.textContent).toContain('review'));
    expect(target.textContent).not.toContain('Collection settings');
    const reportLink = target.querySelector<HTMLAnchorElement>('a.report-row');
    expect(reportLink?.getAttribute('href')).toBe(`/insights/agent-behaviour?report=${api.rows[0].report_id}`);
    const reportId = new URL(reportLink!.href).searchParams.get('report');
    await unmount(component);
    component = mount(PersonalAgentBehaviourView, { target, props: { state, reportId } });
    await vi.waitFor((): void => expect(target.querySelector('article')?.textContent).toContain('The agent retried with a different tool'));
    expect(target.textContent).not.toContain('Delete entry');
    expect(target.querySelector('dialog')).toBeNull();
    expect(target.querySelector('a.admin-back-link')?.getAttribute('href')).toBe('/insights/agent-behaviour');
    await unmount(component);
    component = mount(PersonalAgentBehaviourView, { target, props: { state } });
    await vi.waitFor((): void => expect(list).toHaveBeenCalledTimes(2));
    choose(target, 'Reporting settings', 'Historical review');
    choose(target, 'Pattern', 'Missing context');
    choose(target, 'Status', 'Not observed');
    expect(list).toHaveBeenCalledTimes(2);
    target.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await vi.waitFor((): void => expect(list).toHaveBeenLastCalledWith({ limit: 25, offset: 0, playbook_id: 'review', pattern_id: 'missing-context', status: 'not_observed' }, expect.any(AbortSignal)));
    await vi.waitFor((): void => expect(target.querySelector('.report-row')?.textContent).toContain('Historical review'));
  } finally { await unmount(component); target.remove(); state.dispose(); }
});

test('clears personal entries and filter choices when detail access is lost', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi();
  api.rows = [storedReport()];
  const get = async (): Promise<never> => { throw new HttpError(403, 'Forbidden', null); };
  const state = new PersonalReportsState({ list: api.reports.list, get });
  const target = document.createElement('div'); document.body.append(target);
  const component = mount(PersonalAgentBehaviourView, { target, props: { state, reportId: api.rows[0].report_id } });
  try {
    await vi.waitFor((): void => expect(target.querySelector('[role="alert"]')?.textContent).toContain('Your entries are no longer available'));
    expect(target.querySelector('form, .report-row, dialog')).toBeNull();
    expect(state.reports.reportingOptions).toEqual([]);
  } finally { await unmount(component); target.remove(); state.dispose(); }
});
