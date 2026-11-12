import type { ActivityChart, OperationChart, OutcomeChart } from '$lib/components/shared/dashboard/visualizations/types';
import type { PersonalUsage, UsageCounts } from './domain/usage-schemas';

type OutcomeCounts = UsageCounts['tool'];
type ActivityInput = OutcomeCounts & { readonly date: string };

const outcomeKeys = ['success', 'failure', 'cancelled'] as const;
const categoryKeys = ['tool', 'resource', 'prompt'] as const;
const outcomeLabels = { success: 'Successful', failure: 'Failed', cancelled: 'Cancelled' };
const categoryLabels = { tool: 'Tools', resource: 'Resources', prompt: 'Prompts' };
const zeroCounts: OutcomeCounts = { success: 0, failure: 0, cancelled: 0 };

export function projectOutcomes(counts: OutcomeCounts = zeroCounts): OutcomeChart {
  const total = counts.success + counts.failure + counts.cancelled;
  let offset = 0;
  const segments = outcomeKeys.map((key) => {
    const percentage = total > 0 ? counts[key] / total * 100 : 0;
    const segment = { key, label: outcomeLabels[key], count: counts[key], percentage, offset };
    offset += percentage;
    return segment;
  });
  const successRate = total > 0 ? (counts.success / total * 100).toFixed(1) : '';
  return {
    total, successRate, segments,
    label: total > 0 ? `${successRate}% successful tool calls. ${counts.success} successful, ${counts.failure} failed, ${counts.cancelled} cancelled. ${total} tool calls.` : 'No tool calls'
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

export function projectUsage(snapshot?: PersonalUsage): { outcomes: OutcomeChart; mix: OperationChart; activity: ActivityChart } {
  return {
    outcomes: projectOutcomes(snapshot?.totals.tool),
    mix: projectOperationMix(snapshot?.totals),
    activity: projectActivity(snapshot?.daily.map((row) => ({ date: row.date, ...row.counts.tool })) ?? [])
  };
}
