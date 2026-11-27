import type { RankedTool } from '#lib/components/shared/dashboard/visualizations/types.js';

const clientLabels = {
  'claude-code': 'Claude Code',
  'claude-code-desktop': 'Claude Code Desktop',
  codex: 'Codex',
  codex_exec: 'Codex CLI'
} as const;

export function harnessClientLabel(source: keyof typeof clientLabels): string {
  return clientLabels[source];
}

export function sessionIdentity(key: { source: string; session_id: string }): string {
  return `${key.source}/${key.session_id}`;
}

export function harnessRanking(tools: readonly { tool_name: string; count: number }[]): readonly RankedTool[] {
  const maximum = Math.max(1, ...tools.map((tool): number => tool.count));
  return tools.map((tool): RankedTool => ({
    id: tool.tool_name, name: tool.tool_name, count: tool.count, barWidth: tool.count / maximum * 100
  }));
}
