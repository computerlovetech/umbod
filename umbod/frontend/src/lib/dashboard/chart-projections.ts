import type { ActivityChart, OperationChart, OutcomeChart, OutcomeSegment, RankedTool } from '#lib/components/shared/dashboard/visualizations/types.js';
import type { UsageSummary, UsageCounts } from '#lib/usage/usage-schemas.js';

type OutcomeCounts = UsageCounts['tool'];
type ActivityInput = OutcomeCounts & { readonly date: string };

const outcomeKeys = ['success', 'failure', 'cancelled'] as const;
const categoryKeys = ['tool', 'resource', 'prompt'] as const;
const outcomeLabels = { success: 'Successful', failure: 'Failed', cancelled: 'Cancelled', unknown: 'Unknown' };

type HarnessCounts = { readonly success: number; readonly failure: number; readonly unknown: number };
const categoryLabels = { tool: 'Tools', resource: 'Resources', prompt: 'Prompts' };
const zeroCounts: OutcomeCounts = { success: 0, failure: 0, cancelled: 0 };

export function projectOutcomes(counts: OutcomeCounts | HarnessCounts = zeroCounts): OutcomeChart {
  const keys = 'unknown' in counts ? ['success', 'failure', 'unknown'] as const : outcomeKeys;
  const values: Partial<Record<OutcomeSegment['key'], number>> = counts;
  const total = keys.reduce((sum, key): number => sum + (values[key] ?? 0), 0);
  let offset = 0;
  const segments = keys.map((key): OutcomeSegment => {
    const count = values[key] ?? 0;
    const percentage = total > 0 ? count / total * 100 : 0;
    const segment = { key, label: outcomeLabels[key], count, percentage, offset };
    offset += percentage;
    return segment;
  });
  const successRate = total > 0 ? (counts.success / total * 100).toFixed(1) : '';
  const breakdown = segments.map((segment): string => `${segment.count} ${segment.label.toLowerCase()}`).join(', ');
  return {
    total, successRate, segments,
    label: total > 0 ? `${successRate}% successful tool calls. ${breakdown}. ${total} tool calls.` : 'No tool calls'
  };
}

export function projectOperationMix(counts?: UsageCounts): OperationChart {
  const categories = categoryKeys.map((key) => ({
    key, label: categoryLabels[key],
    count: outcomeKeys.reduce((sum, outcome): number => sum + (counts?.[key][outcome] ?? 0), 0)
  }));
  const total = categories.reduce((sum, category): number => sum + category.count, 0);
  const segments = categories.map((category) => ({ ...category, share: total > 0 ? category.count / total * 100 : 0 }));
  return { total, segments, label: total > 0 ? segments.map((item): string => `${item.label}: ${item.count} (${item.share.toFixed(1)}%)`).join(', ') : 'No operations' };
}

export function projectActivity(rows: readonly ActivityInput[]): ActivityChart {
  const days = rows.map((row) => ({
    ...row,
    label: new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', timeZone: 'UTC' }).format(new Date(row.date)),
    total: row.success + row.failure + row.cancelled
  }));
  const total = days.reduce((sum, day): number => sum + day.total, 0);
  const axisMaximum = Math.max(50, Math.ceil(Math.max(0, ...days.map((day): number => day.total)) / 50) * 50);
  return { days, axisMaximum, total, label: `Daily tool calls for ${days.length} days. ${total} tool calls in total. UTC.` };
}

export function projectUsage(snapshot?: UsageSummary): { outcomes: OutcomeChart; mix: OperationChart; activity: ActivityChart; tools: readonly RankedTool[] } {
  const topTools = snapshot?.top_tools ?? [];
  const maximumCount = Math.max(0, ...topTools.map((tool): number => tool.count));
  return {
    tools: topTools.map((tool): RankedTool => ({
      id: tool.tool_id, name: tool.tool_name, connector: tool.connector_name,
      count: tool.count, barWidth: tool.count / maximumCount * 100
    })),
    outcomes: projectOutcomes(snapshot?.totals.tool),
    mix: projectOperationMix(snapshot?.totals),
    activity: projectActivity(snapshot?.daily.map((row) => ({ date: row.date, ...row.counts.tool })) ?? [])
  };
}
