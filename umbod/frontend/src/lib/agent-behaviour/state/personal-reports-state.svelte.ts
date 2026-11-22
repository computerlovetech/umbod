import { SvelteMap } from 'svelte/reactivity';
import type { ReportReadsPort } from '../api';
import type { DiagnosticReport, ReportPage } from '../domain/schemas';
import { personalAgentBehaviourApi } from '../infrastructure/personal-api';
import { ReportsState, type ReportLabel, type ReportLabels } from './reports-state.svelte';

class PersonalReportLabels implements ReportLabels {
  private readonly patternNames = new SvelteMap<string, string>();
  private readonly playbookNames = new SvelteMap<string, string>();

  get patterns(): readonly ReportLabel[] {
    return Array.from(this.patternNames, ([id, name]): ReportLabel => ({ id, name }));
  }

  get playbooks(): readonly ReportLabel[] {
    return Array.from(this.playbookNames, ([id, name]): ReportLabel => ({ id, name }));
  }

  seenPage = (page: ReportPage): void => {
    for (const report of page.items) {
      if (!this.playbookNames.has(report.playbook_id)) this.playbookNames.set(report.playbook_id, report.playbook_id);
      for (const id of report.observed_pattern_ids) {
        if (!this.patternNames.has(id)) this.patternNames.set(id, id);
      }
    }
  };

  seenDetail = (detail: DiagnosticReport): void => {
    this.playbookNames.set(detail.instructions.playbook.id, detail.instructions.playbook.name);
    for (const pattern of detail.instructions.patterns) this.patternNames.set(pattern.id, pattern.name);
    for (const { pattern_id: id } of detail.submission.assessments) {
      if (!this.patternNames.has(id)) this.patternNames.set(id, id);
    }
  };

  clear = (): void => {
    this.patternNames.clear();
    this.playbookNames.clear();
  };
}

export class PersonalReportsState {
  private accessAllowed = $state(true);
  readonly reports: ReportsState;

  constructor(api: ReportReadsPort, private readonly onAccessLost?: () => void) {
    const labels = new PersonalReportLabels();
    this.reports = new ReportsState(api, this.revoke, () => labels);
  }

  get allowed(): boolean { return this.accessAllowed; }

  private revoke = (): void => {
    if (!this.accessAllowed) return;
    this.dispose();
    this.onAccessLost?.();
  };

  dispose = (): void => {
    this.accessAllowed = false;
    this.reports.dispose();
  };
}

export function createPersonalReportsState(onAccessLost?: () => void): PersonalReportsState {
  return new PersonalReportsState(personalAgentBehaviourApi().reports, onAccessLost);
}
