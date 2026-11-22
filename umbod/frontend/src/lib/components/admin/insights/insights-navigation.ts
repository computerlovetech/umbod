import { agentBehaviourFindingsHref, agentDiagnosticsHref } from '#lib/workspace/navigation.js';
import type { SubpageLink } from '#lib/components/shared/workspace/SubpageNavigation.svelte';

export const insightsLinks: readonly SubpageLink[] = [
  { id: 'behaviour', label: 'Agent behaviour', href: agentBehaviourFindingsHref },
  { id: 'logs', label: 'Log analytics', href: '/admin/insights/logs' }
];

export class InsightsNavigation {
  constructor(private readonly pathname: () => string) {}
  get diagnostics(): boolean { return this.pathname() === agentDiagnosticsHref; }
  get activeId(): 'behaviour' | 'logs' { return this.pathname() === '/admin/insights/logs' ? 'logs' : 'behaviour'; }
}
