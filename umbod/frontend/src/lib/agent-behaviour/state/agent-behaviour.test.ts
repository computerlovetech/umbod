import { describe, expect, test, vi } from 'vitest';
import { HttpError } from '#lib/admin/infrastructure/transport.js';
import { InMemoryAgentBehaviourApi, deferred } from '../in-memory.test-support';
import { ConfigurationState } from './configuration-state.svelte';
import { ReportsState } from './reports-state.svelte';
import { AdminReportsState } from './admin-reports-state.svelte';
import { AgentBehaviourPageState } from './page-state.svelte';
import type { Configuration, DiagnosticReport, ReportPage } from '../domain/schemas';

const configuration: Configuration = { revision: 1, reporting_enabled: false, patterns: [{ id: 'fallback', name: 'Fallback', description: 'Description', assessment_prompt: 'Assess facts', inclusion_criteria: 'Include', exclusion_criteria: 'Exclude', categories: ['quality'], polarity: 'negative', enabled: true }], playbooks: [{ id: 'review', name: 'Review', collection_instructions: 'Collect facts', pattern_ids: ['fallback'], enabled: true }] };
const report: DiagnosticReport = { report_id: '00000000-0000-4000-8000-000000000001', received_at: '2026-06-01T00:00:00Z', expires_at: '2026-07-01T00:00:00Z', caller: { authentication: 'local_test', subject: { issuer: { value: 'test' }, subject: 'admin' } }, submission: { idempotency_key: '00000000-0000-4000-8000-000000000002', configuration_revision: 1, playbook_id: 'review', trigger: 'user_requested', assessments: [{ pattern_id: 'fallback', status: 'observed', summary: '<script>unsafe</script>', evidence: ['<img src=x onerror=alert(1)>'] }] }, instructions: { configuration_revision: 1, playbook: configuration.playbooks[0], patterns: configuration.patterns, reporting_guidance: 'Only authorized facts', resource_uri: 'umbod://agent-behaviour/playbooks/review' } };

describe('pattern editing', (): void => {
  function setup(): { api: InMemoryAgentBehaviourApi; state: ConfigurationState } {
    const api = new InMemoryAgentBehaviourApi();
    api.current = structuredClone(configuration);
    api.defaults = structuredClone(configuration);
    return { api, state: new ConfigurationState(api.configuration, vi.fn(), (): string => 'pattern-stable') };
  }
  test('generates stable internal IDs and derives the assessment prompt', async (): Promise<void> => {
    const { api, state } = setup(); await state.load(); state.addPattern();
    expect(state.selected?.id).toBe('pattern-stable');
    state.updatePattern('pattern-stable', 'name', 'New name');
    state.updatePattern('pattern-stable', 'description', 'Notice missing facts');
    state.updatePattern('pattern-stable', 'name', 'Renamed');
    await state.savePatternEdit();
    expect(state.patterns[1].id).toBe('pattern-stable');
    expect(state.patterns[1].assessment_prompt).toBe('Notice missing facts');
    expect(state.dirty).toBe(true); await state.save();
    expect(api.current.patterns[1].name).toBe('Renamed');
    expect(api.current.playbooks[0].pattern_ids).toContain('pattern-stable');
    expect(state.dirty).toBe(false);
  });
  test('plain description edits update default assessments but preserve explicit advanced overrides', async (): Promise<void> => {
    const { api, state } = setup();
    api.current.patterns[0].assessment_prompt = api.current.patterns[0].description;
    await state.load();
    state.updatePattern('fallback', 'description', 'Updated default criteria');
    expect(state.patterns[0].assessment_prompt).toBe('Updated default criteria');
    state.updatePattern('fallback', 'assessment_prompt', 'An explicit expert override');
    state.updatePattern('fallback', 'description', 'Another description');
    await state.save();
    expect(api.current.patterns[0].description).toBe('Another description');
    expect(api.current.patterns[0].assessment_prompt).toBe('An explicit expert override');
  });
  test('persists reporting intent and memberships across all-disabled and all-removed save and reload', async (): Promise<void> => {
    const { api, state } = setup();
    const second = { ...configuration.patterns[0], id: 'second', name: 'Second pattern' };
    api.current.patterns.push(second);
    api.current.playbooks.push({ ...configuration.playbooks[0], id: 'custom-reporting', name: 'Custom reporting', pattern_ids: ['second'] });
    const memberships = structuredClone(api.current.playbooks);
    api.current.reporting_enabled = true;
    await state.load();
    state.updatePattern('fallback', 'enabled', false); state.updatePattern('second', 'enabled', false);
    expect(state.reportingNeedsUsablePlaybook).toBe(true); await state.save();
    expect(state.playbooks).toEqual(memberships); expect(state.playbooks).toEqual(api.current.playbooks); expect(state.dirty).toBe(false);
    state.dispose();
    const reloaded = new ConfigurationState(api.configuration, vi.fn()); await reloaded.load();
    expect(reloaded.playbooks).toEqual(memberships); expect(reloaded.reportingNeedsUsablePlaybook).toBe(true);
    const defaults = vi.spyOn(api.configuration, 'defaults');
    reloaded.updatePattern('fallback', 'enabled', true);
    expect(reloaded.reportingNeedsUsablePlaybook).toBe(false); expect(defaults).not.toHaveBeenCalled();
    await reloaded.save(); expect(reloaded.playbooks).toEqual(memberships);
    reloaded.removePattern('fallback'); reloaded.removePattern('second'); await reloaded.save();
    expect(api.current.patterns).toEqual([]); expect(api.current.playbooks).toEqual(memberships);
    expect(reloaded.settings).toEqual(api.current.playbooks); expect(reloaded.reportingNeedsUsablePlaybook).toBe(true); expect(reloaded.dirty).toBe(false);
    reloaded.dispose();
    const afterRemoval = new ConfigurationState(api.configuration, vi.fn()); await afterRemoval.load();
    expect(afterRemoval.patterns).toEqual([]);
    expect(afterRemoval.playbooks).toEqual(memberships); expect(afterRemoval.savedReportingEnabled).toBe(true); expect(afterRemoval.reportingNeedsUsablePlaybook).toBe(true);
    expect(afterRemoval.dirty).toBe(false); expect(defaults).not.toHaveBeenCalled();
  });
  test('never turns saved reporting Off back on when enabling or adding patterns after reload', async (): Promise<void> => {
    const { api, state } = setup();
    api.current.playbooks.push({ ...configuration.playbooks[0], id: 'custom-reporting', name: 'Custom reporting', enabled: false });
    api.current.reporting_enabled = true;
    await state.load();
    state.setReportingEnabled(false);
    const playbooks = structuredClone(api.current.playbooks);
    state.updatePattern('fallback', 'enabled', false); await state.save(); state.dispose();
    const reloaded = new ConfigurationState(api.configuration, vi.fn()); await reloaded.load();
    const defaults = vi.spyOn(api.configuration, 'defaults');
    reloaded.updatePattern('fallback', 'enabled', true); await reloaded.save();
    expect(defaults).not.toHaveBeenCalled(); expect(reloaded.savedReportingEnabled).toBe(false);
    expect(api.current.playbooks).toEqual(playbooks);
    reloaded.removePattern('fallback'); await reloaded.save(); reloaded.dispose();
    const afterRemoval = new ConfigurationState(api.configuration, vi.fn(), (): string => 'new-pattern'); await afterRemoval.load();
    afterRemoval.addPattern();
    afterRemoval.updatePattern('new-pattern', 'name', 'New pattern');
    afterRemoval.updatePattern('new-pattern', 'description', 'Notice new facts');
    await afterRemoval.savePatternEdit(); await afterRemoval.save();
    expect(afterRemoval.savedReportingEnabled).toBe(false);
    expect(api.current.patterns.map((pattern): string => pattern.id)).toEqual(['new-pattern']);
    expect(api.current.playbooks[0]).toEqual({ ...playbooks[0], pattern_ids: ['fallback', 'new-pattern'] });
    expect(api.current.playbooks[1]).toEqual(playbooks[1]);
    expect(defaults).not.toHaveBeenCalled();
  });
  test('keeps profiles and collection instructions authoritative when every referenced pattern is removed', async (): Promise<void> => {
    const { api, state } = setup(); await state.load(); state.updateCollectionInstructions('review', 'Keep these instructions');
    state.removePattern('fallback'); await state.save();
    expect(state.playbooks).toEqual(api.current.playbooks); expect(state.settings).toHaveLength(1);
    expect(state.settings[0]).toEqual(expect.objectContaining({ enabled: true, pattern_ids: ['fallback'], collection_instructions: 'Keep these instructions' }));
    expect(state.savedReportingEnabled).toBe(false); expect(state.dirty).toBe(false);
    await state.load();
    expect(state.patterns).toEqual([]);
    expect(state.settings[0].collection_instructions).toBe('Keep these instructions');
    expect(state.playbooks).toEqual(api.current.playbooks);
  });
  test('warns only while enabled and requires an enabled playbook with an enabled member', async (): Promise<void> => {
    const { api, state } = setup();
    api.current.patterns[0].enabled = false;
    api.current.patterns.push({ ...configuration.patterns[0], id: 'unrelated' });
    api.current.playbooks.push({ ...configuration.playbooks[0], id: 'disabled', enabled: false, pattern_ids: ['unrelated'] });
    await state.load();
    expect(state.reportingNeedsUsablePlaybook).toBe(false);
    state.setReportingEnabled(true);
    expect(state.reportingNeedsUsablePlaybook).toBe(true);
    state.updatePattern('fallback', 'enabled', true);
    expect(state.reportingNeedsUsablePlaybook).toBe(false);
    state.removePattern('fallback');
    expect(state.reportingNeedsUsablePlaybook).toBe(true);
  });
  test('restores a single excluded playbook only by explicit inclusion', async (): Promise<void> => {
    const { api, state } = setup();
    api.current.playbooks[0].enabled = false;
    await state.load();
    state.setReportingEnabled(true);
    expect(state.reportingNeedsUsablePlaybook).toBe(true);
    expect(state.playbooks[0].enabled).toBe(false);
    state.setPlaybookIncluded('review', true);
    expect(state.reportingNeedsUsablePlaybook).toBe(false);
    state.setPlaybookIncluded('review', false);
    expect(state.playbooks[0].enabled).toBe(true);
    await state.save();
    expect(api.current.reporting_enabled).toBe(true);
    expect(api.current.playbooks).toEqual(configuration.playbooks);
  });
  test('initializes only reporting defaults when the first pattern is saved in the editor', async (): Promise<void> => {
    const { api, state } = setup(); api.current = { revision: 1, reporting_enabled: false, patterns: [], playbooks: [] };
    const defaults = vi.spyOn(api.configuration, 'defaults');
    await state.load(); state.addPattern();
    state.updatePattern('pattern-stable', 'name', 'Abandoned pattern');
    state.closeEditor();
    expect(state.selected).toBeUndefined(); expect(state.dirty).toBe(false);
    expect(state.patterns).toEqual([]); expect(state.settings).toEqual([]); expect(defaults).not.toHaveBeenCalled();
    state.addPattern();
    state.updatePattern('pattern-stable', 'name', 'New pattern'); state.updatePattern('pattern-stable', 'description', 'Notice facts');
    await state.savePatternEdit();
    expect(defaults).toHaveBeenCalledOnce();
    expect(state.patterns.map((pattern): string => pattern.id)).toEqual(['pattern-stable']);
    expect(state.settings[0]).toEqual(expect.objectContaining({ pattern_ids: ['pattern-stable'], enabled: true }));
    await state.save(); expect(api.current.reporting_enabled).toBe(false); expect(api.current.patterns).toHaveLength(1); expect(api.current.playbooks[0].pattern_ids).toEqual(['pattern-stable']);
  });
  test('uses pattern names and plain labels rather than internal validation paths', async (): Promise<void> => {
    const { state } = setup(); await state.load(); await state.updatePattern('fallback', 'categories', ['INVALID_CATEGORY']); await state.save();
    expect(state.message).toContain('Fallback'); expect(state.message).toContain('category labels');
    expect(state.message).not.toContain('patterns.'); expect(state.message).not.toContain('fallback'); expect(state.message).not.toContain('INVALID_CATEGORY');
    state.discard(); state.addPattern(); state.updatePattern('pattern-stable', 'description', 'Notice facts');
    await state.savePatternEdit();
    expect(state.editorMessage).toContain('Add a name'); expect(state.editorMessage).not.toContain('assessment_prompt');
    expect(state.selected?.description).toBe('Notice facts'); expect(state.patterns).toHaveLength(1); expect(state.dirty).toBe(false);
  });
  test('does not repopulate a deliberately empty configuration on load', async (): Promise<void> => {
    const { api, state } = setup(); api.current = { revision: 3, reporting_enabled: false, patterns: [], playbooks: [] };
    const defaults = vi.spyOn(api.configuration, 'defaults'); await state.load();
    expect(state.patterns).toEqual([]); expect(state.settings).toEqual([]);
    expect(state.dirty).toBe(false); expect(defaults).not.toHaveBeenCalled();
  });
  test('preserves named custom reporting settings and configured references', async (): Promise<void> => {
    const { api, state } = setup(); api.current.playbooks.push({ ...configuration.playbooks[0], id: 'custom-review', name: 'Custom reporting' });
    await state.load(); state.removePattern('fallback'); expect(state.playbooks).toHaveLength(2);
    expect(state.playbooks.every((setting): boolean => setting.pattern_ids.includes('fallback'))).toBe(true);
    await state.save();
    expect(api.current.patterns).toEqual([]);
    expect(api.current.playbooks.find((setting): boolean => setting.id === 'custom-review')).toEqual(expect.objectContaining({ name: 'Custom reporting', pattern_ids: ['fallback'] }));
  });
  test('preserves edits on conflict until explicit discard', async (): Promise<void> => {
    const { api, state } = setup(); await state.load();
    state.updatePattern('fallback', 'name', 'Local edit');
    api.current = { ...configuration, revision: 2, reporting_enabled: true };
    await state.save();
    expect(state.patterns[0].name).toBe('Local edit'); expect(state.conflict).toBe(true);
    state.addPattern(); state.closeEditor();
    expect(state.message).toContain('Another administrator saved changes');
    expect(state.reportingEnabled).toBe(false);
    expect(state.savedReportingEnabled).toBe(true);
    state.discard(); expect(state.revision).toBe(2); expect(state.patterns[0].name).toBe('Fallback');
    expect(state.reportingEnabled).toBe(state.savedReportingEnabled);
  });
  test('discard resets the draft without a request', async (): Promise<void> => {
    const { state } = setup(); await state.load(); state.removePattern('fallback'); state.discard();
    expect(state.patterns).toHaveLength(1); expect(state.dirty).toBe(false);
  });
  test('rejects duplicate generated identifiers and pattern limits without truncation', async (): Promise<void> => {
    const { api, state } = setup(); api.current.patterns = Array.from({ length: 50 }, (_, index): Configuration['patterns'][number] => ({ ...configuration.patterns[0], id: `pattern-${index}` })); api.current.playbooks = [];
    await state.load(); state.addPattern(); expect(state.patterns).toHaveLength(50); expect(state.message).toContain('50');
    state.removePattern('pattern-0'); state.addPattern();
    state.updatePattern('pattern-stable', 'name', 'Replacement'); state.updatePattern('pattern-stable', 'description', 'Notice facts');
    await state.savePatternEdit();
    state.addPattern(); expect(state.patterns).toHaveLength(50); expect(state.selected).toBeUndefined();
  });
  test('rejects invalid and duplicate generated IDs without adding patterns', async (): Promise<void> => {
    const api = new InMemoryAgentBehaviourApi(); api.current = structuredClone(configuration);
    for (const id of ['fallback', 'INVALID ID']) {
      const state = new ConfigurationState(api.configuration, vi.fn(), (): string => id); await state.load(); state.addPattern();
      expect(state.patterns).toHaveLength(1); expect(state.message).toContain('identifier'); state.dispose();
    }
  });
  test('blocks additions beyond reporting capacity', async (): Promise<void> => {
    const { api, state } = setup(); api.current.patterns = Array.from({ length: 20 }, (_, index): Configuration['patterns'][number] => ({ ...configuration.patterns[0], id: `pattern-${index}` })); api.current.playbooks[0].pattern_ids = api.current.patterns.map((pattern): string => pattern.id);
    await state.load(); state.addPattern(); expect(state.patterns).toHaveLength(20); expect(state.message).toContain('20');
  });
  test('can replace removed patterns at capacity without losing reporting preferences', async (): Promise<void> => {
    const { api, state } = setup(); api.current.patterns = [];
    api.current.playbooks[0].pattern_ids = Array.from({ length: 20 }, (_, index): string => `retired-${index}`);
    api.current.playbooks[0].enabled = false;
    const settings = structuredClone(api.current.playbooks[0]);
    await state.load(); state.addPattern();
    expect(state.playbooks[0]).toEqual(settings);
    state.updatePattern('pattern-stable', 'name', 'Replacement'); state.updatePattern('pattern-stable', 'description', 'Notice replacement facts');
    await state.savePatternEdit();
    expect(state.patterns).toHaveLength(1); expect(state.message).toContain('removed patterns were cleared');
    await state.save();
    expect(api.current.playbooks[0]).toEqual({ ...settings, pattern_ids: ['pattern-stable'] });
    expect(state.savedReportingEnabled).toBe(false);
  });
  test('rejects newly invented unknown references at the historical persistence boundary', async (): Promise<void> => {
    const { api } = setup();
    await expect(api.configuration.publish({ expected_revision: 1, reporting_enabled: false, patterns: [], playbooks: [{ ...configuration.playbooks[0], pattern_ids: ['invented'] }] })).rejects.toBeInstanceOf(HttpError);
    expect(api.current.revision).toBe(1);
    await expect(api.configuration.publish({ expected_revision: 1, reporting_enabled: false, patterns: [], playbooks: configuration.playbooks })).resolves.toEqual(expect.objectContaining({ patterns: [], playbooks: configuration.playbooks }));
  });
  test('disposal fences configuration, pattern creation and save responses', async (): Promise<void> => {
    const { api, state } = setup(); const response = deferred<Configuration>(); vi.spyOn(api.configuration, 'get').mockReturnValue(response.promise);
    const pending = state.load(); state.dispose(); response.resolve(configuration); await pending; expect(state.loaded).toBe(false); expect(state.patterns).toEqual([]);
    const second = setup(); second.api.current.playbooks = []; await second.state.load(); const defaults = deferred<Configuration>(); vi.spyOn(second.api.configuration, 'defaults').mockReturnValue(defaults.promise);
    second.state.addPattern(); second.state.updatePattern('pattern-stable', 'name', 'New pattern'); second.state.updatePattern('pattern-stable', 'description', 'Notice facts');
    const adding = second.state.savePatternEdit(); second.state.dispose(); defaults.resolve(configuration); await adding; expect(second.state.patterns).toEqual([]); expect(second.state.settings).toEqual([]);
    const third = setup(); await third.state.load(); const published = deferred<Configuration>(); vi.spyOn(third.api.configuration, 'publish').mockReturnValue(published.promise);
    const saving = third.state.save(); third.state.dispose(); published.resolve(configuration); await saving; expect(third.state.loaded).toBe(false);
  });
  test('pending saves fence further edits', async (): Promise<void> => {
    const { api, state } = setup(); await state.load(); const response = deferred<Configuration>(); vi.spyOn(api.configuration, 'publish').mockReturnValue(response.promise);
    const saving = state.save(); state.removePattern('fallback'); state.updatePattern('fallback', 'name', 'Ignored');
    response.resolve(configuration); await saving; expect(state.patterns[0].name).toBe('Fallback');
  });
  test('access failures clear editors and report content', async (): Promise<void> => {
    const api = new InMemoryAgentBehaviourApi(); api.current = configuration; api.rows = [report]; const state = new AgentBehaviourPageState(api); await state.configuration.load(); await state.reports.open(report.report_id);
    vi.spyOn(api.configuration, 'publish').mockRejectedValue(new HttpError(403, 'Forbidden', null)); await state.configuration.save(); expect(state.allowed).toBe(false); expect(state.configuration.patterns).toEqual([]); expect(state.reports.detail).toBeNull();
  });
});

describe('report inspection', (): void => {
  test('keeps draft filters separate from applied pagination and resets without I/O', async (): Promise<void> => {
    const api = new InMemoryAgentBehaviourApi();
    const list = vi.spyOn(api.reports, 'list');
    const state = new ReportsState(api.reports, vi.fn(), () => ({ patterns: configuration.patterns, playbooks: configuration.playbooks }));
    expect(state.querySummary).toBe('All reporting settings · All patterns · All statuses');
    state.filter('pattern_id', 'fallback'); state.filter('status', 'observed');
    expect(list).not.toHaveBeenCalled();
    expect(state.query.pattern_id).toBeUndefined();
    expect(await state.runQuery()).toBe(true);
    expect(state.querySummary).toBe('All reporting settings · Fallback · Observed');
    state.filter('status', 'not_observed');
    state.paginate(1); await vi.waitFor((): void => expect(state.busy).toBe(false));
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'observed', offset: 25 }), expect.anything());
    const count = list.mock.calls.length;
    state.resetQuery();
    expect(state.draftQuery).toEqual({ limit: 25, offset: 0 });
    expect(state.query.status).toBe('observed');
    expect(state.querySummary).toBe('All reporting settings · Fallback · Observed');
    expect(list).toHaveBeenCalledTimes(count);
    state.dispose();
  });
  test('uses published configuration rather than unsaved names and removals', async (): Promise<void> => {
    const api = new InMemoryAgentBehaviourApi(); api.current = structuredClone(configuration);
    const state = new AgentBehaviourPageState(api); await state.configuration.load();
    state.configuration.updatePattern('fallback', 'name', 'Unsaved name');
    expect(state.reports.patternName('fallback')).toBe('Fallback');
    state.configuration.removePattern('fallback');
    expect(state.reports.patterns).toHaveLength(1);
    await state.configuration.save();
    expect(state.reports.patterns).toEqual([]);
    state.dispose();
  });
  test('stop fences pending reads and closes detail while start restores the applied query', async (): Promise<void> => {
    const api = new InMemoryAgentBehaviourApi(); api.rows = [report];
    const response = deferred<ReportPage>();
    const list = vi.spyOn(api.reports, 'list').mockReturnValueOnce(response.promise);
    const state = new AdminReportsState(api.reports, vi.fn());
    state.filter('status', 'observed');
    const pending = state.runQuery();
    await state.open(report.report_id); state.confirmDelete();
    state.stop();
    expect(list.mock.calls[0][1]?.aborted).toBe(true);
    response.resolve({ items: [], total: 99 });
    expect(await pending).toBe(false);
    expect(state.page.total).toBe(0); expect(state.busy).toBe(false);
    expect(state.detail).toBeNull(); expect(state.deleteConfirmation).toBe(false);
    state.start(); await vi.waitFor((): void => expect(state.busy).toBe(false));
    expect(state.query).toEqual({ limit: 25, offset: 0, status: 'observed' });
    expect(state.draftQuery).toEqual({ limit: 25, offset: 0, status: 'observed' });
    expect(state.page.total).toBe(1);
    state.dispose();
    expect(await state.runQuery()).toBe(false);
  });
  test('only the current successful query returns true and stale failures cannot revoke access', async (): Promise<void> => {
    const api = new InMemoryAgentBehaviourApi();
    const first = deferred<ReportPage>(); const revoke = vi.fn();
    vi.spyOn(api.reports, 'list').mockReturnValueOnce(first.promise.then((): ReportPage => { throw new HttpError(403, 'Forbidden', null); }));
    const state = new ReportsState(api.reports, revoke);
    const pending = state.runQuery();
    expect(await state.runQuery()).toBe(true);
    first.resolve({ items: [], total: 99 });
    expect(await pending).toBe(false); expect(revoke).not.toHaveBeenCalled();
    state.dispose();
  });
  test('retains original snapshots and requires confirmation before deletion', async (): Promise<void> => {
    const api = new InMemoryAgentBehaviourApi(); api.rows = [report]; const state = new AdminReportsState(api.reports, vi.fn()); await state.load(); await state.open(report.report_id); api.current = { ...configuration, revision: 8 };
    expect(state.detail?.instructions.configuration_revision).toBe(1); expect(await state.remove()).toBe(false); expect(api.rows).toHaveLength(1); state.confirmDelete(); expect(await state.remove()).toBe(true); expect(api.rows).toHaveLength(0); expect(state.detail).toBeNull();
  });
  test('a deletion finishing after leaving the report does not request navigation', async (): Promise<void> => {
    const api = new InMemoryAgentBehaviourApi(); api.rows = [report];
    const response = deferred<void>();
    const remove = vi.spyOn(api.reports, 'remove').mockReturnValue(response.promise);
    const state = new AdminReportsState(api.reports, vi.fn());
    await state.open(report.report_id);
    state.confirmDelete();
    const pending = state.remove();
    state.close();
    response.resolve(undefined);
    expect(remove.mock.calls[0][1]?.aborted).toBe(true);
    expect(await pending).toBe(false);
  });
  test('filters same assessments and resets offset', async (): Promise<void> => {
    const api = new InMemoryAgentBehaviourApi(); api.rows = [report]; const state = new ReportsState(api.reports, vi.fn()); await state.load(); state.paginate(1); await vi.waitFor((): void => expect(state.busy).toBe(false)); state.filter('status', 'not_assessed'); expect(state.query.offset).toBe(25); await state.runQuery(); expect(state.query.offset).toBe(0); expect(state.page.total).toBe(0);
  });
  test('uses current names only for known IDs and saved names for historical details', async (): Promise<void> => {
    const api = new InMemoryAgentBehaviourApi(); api.rows = [report]; const state = new ReportsState(api.reports, vi.fn(), () => ({ patterns: [{ id: 'new-pattern', name: 'Unrelated current name' }], playbooks: [] }));
    expect(state.patternName('fallback')).toBe('Removed pattern'); expect(state.reportingName('review')).toBe('Previous reporting settings');
    await state.open(report.report_id); expect(state.assessments[0].pattern?.name).toBe('Fallback');
    state.dispose(); const listing = vi.spyOn(api.reports, 'list'); state.filter('pattern_id', 'new-pattern'); await state.load(); expect(listing).not.toHaveBeenCalled();
  });
  test('invalid report links do not request an entry', async (): Promise<void> => {
    const api = new InMemoryAgentBehaviourApi();
    const get = vi.spyOn(api.reports, 'get');
    const state = new ReportsState(api.reports, vi.fn());
    await state.open('..');
    expect(get).not.toHaveBeenCalled();
    expect(state.detail).toBeNull();
    expect(state.message).toBe('This entry is no longer available.');
  });
  test('ignores superseded list and detail responses', async (): Promise<void> => {
    const api = new InMemoryAgentBehaviourApi(); const old = deferred<ReportPage>(); vi.spyOn(api.reports, 'list').mockReturnValueOnce(old.promise); const state = new ReportsState(api.reports, vi.fn()); const pending = state.load(); await state.load(); old.resolve({ items: [], total: 99 }); await pending; expect(state.page.total).toBe(0);
    const detail = deferred<DiagnosticReport>(); vi.spyOn(api.reports, 'get').mockReturnValue(detail.promise); const opening = state.open(report.report_id); state.close(); detail.resolve(report); await opening; expect(state.detail).toBeNull();
  });
});
