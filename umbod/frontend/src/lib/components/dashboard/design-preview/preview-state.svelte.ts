import { projectActivity, projectOperationMix, projectOutcomes } from '$lib/dashboard/chart-projections';
import type { ActivityChart, OperationChart, OutcomeChart, RankedTool } from '$lib/components/shared/dashboard/visualizations/types';

export type PreviewPeriod = 7 | 30;
export type PreviewScenario = 'sample' | 'empty';
export type PreviewConnector = 'GitHub' | 'Slack' | 'Notion';

const sampleTools: readonly { id: string; name: string; connector: PreviewConnector; share: number }[] = [
  { id: 'github-search', name: 'search', connector: 'GitHub', share: 28 },
  { id: 'slack-search', name: 'search', connector: 'Slack', share: 20 },
  { id: 'notion-fetch', name: 'fetch_page', connector: 'Notion', share: 15 },
  { id: 'github-issues', name: 'list_issues', connector: 'GitHub', share: 12 },
  { id: 'slack-send', name: 'send_message', connector: 'Slack', share: 10 },
  { id: 'github-pull-requests', name: 'get_pull_request', connector: 'GitHub', share: 7 },
  { id: 'notion-search', name: 'search', connector: 'Notion', share: 5 },
  { id: 'notion-create', name: 'create_page', connector: 'Notion', share: 3 }
];

type DailyActivity = {
  readonly date: string;
  readonly success: number;
  readonly failure: number;
  readonly cancelled: number;
};

const sampleDays: readonly DailyActivity[] = Array.from({ length: 30 }, (_, index: number): DailyActivity => ({
  date: `2026-11-${String(index + 1).padStart(2, '0')}`,
  success: [120, 164, 138, 190, 108, 74, 92, 150, 180, 144][index % 10],
  failure: [4, 7, 3, 12, 8, 2, 3][index % 7],
  cancelled: index % 4 === 0 ? 2 : 0
}));

export class DashboardPreviewState {
  private selectedPeriod = $state<PreviewPeriod>(7);
  private selectedScenario = $state<PreviewScenario>('sample');
  private selectedConnectorNames = $state<readonly PreviewConnector[]>(['GitHub', 'Slack', 'Notion']);

  get scenario(): PreviewScenario {
    return this.selectedScenario;
  }

  setScenario = (scenario: PreviewScenario): void => {
    this.selectedScenario = scenario;
  };

  get outcomeChart(): OutcomeChart {
    return projectOutcomes(this.totals);
  }

  get activityChart(): ActivityChart {
    return projectActivity(this.days);
  }

  get operationChart(): OperationChart {
    const tool = this.totals;
    return projectOperationMix({
      tool,
      resource: { success: Math.round(tool.all * 16 / 78), failure: 0, cancelled: 0 },
      prompt: { success: Math.round(tool.all * 6 / 78), failure: 0, cancelled: 0 }
    });
  }

  get connectors(): readonly PreviewConnector[] {
    return ['GitHub', 'Slack', 'Notion'];
  }

  get selectedConnectors(): readonly PreviewConnector[] {
    return [...this.selectedConnectorNames];
  }

  get topTools(): readonly RankedTool[] {
    if (this.selectedScenario === 'empty') return [];
    const counts = sampleTools.map((tool): number => Math.floor(this.totals.all * tool.share / 100));
    const remainder = this.totals.all - counts.reduce((sum: number, count: number): number => sum + count, 0);
    const ranked = sampleTools.map((tool, index): Omit<RankedTool, 'barWidth'> => ({
      id: tool.id,
      name: tool.name,
      connector: tool.connector,
      count: counts[index] + (index === 0 ? remainder : 0)
    })).filter((tool): boolean => this.selectedConnectorNames.some((connector): boolean => connector === tool.connector))
      .sort((first, second): number => second.count - first.count || first.id.localeCompare(second.id))
      .slice(0, 5);
    const maximum = ranked[0]?.count ?? 0;
    return ranked.map((tool): RankedTool => ({ ...tool, barWidth: maximum > 0 ? tool.count / maximum * 100 : 0 }));
  }

  setConnectorSelected = (connector: PreviewConnector, selected: boolean): void => {
    this.selectedConnectorNames = this.connectors.filter((name): boolean => name === connector ? selected : this.selectedConnectorNames.includes(name));
  };

  selectAllConnectors = (): void => {
    this.selectedConnectorNames = this.connectors;
  };

  get period(): PreviewPeriod {
    return this.selectedPeriod;
  }

  get days(): readonly DailyActivity[] {
    const days = sampleDays.slice(-this.selectedPeriod);
    return this.selectedScenario === 'empty'
      ? days.map((day): DailyActivity => ({ date: day.date, success: 0, failure: 0, cancelled: 0 }))
      : days;
  }

  get totals(): { success: number; failure: number; cancelled: number; all: number } {
    const success = this.days.reduce((sum: number, day: DailyActivity): number => sum + day.success, 0);
    const failure = this.days.reduce((sum: number, day: DailyActivity): number => sum + day.failure, 0);
    const cancelled = this.days.reduce((sum: number, day: DailyActivity): number => sum + day.cancelled, 0);
    return { success, failure, cancelled, all: success + failure + cancelled };
  }

  setPeriod = (period: PreviewPeriod): void => {
    this.selectedPeriod = period;
  };
}
