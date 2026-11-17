import type { SubpageLink } from '#lib/components/shared/workspace/SubpageNavigation.svelte';

export const insightsLinks: readonly SubpageLink[] = [
  { id: 'behaviour', label: 'Agent behaviour', href: '/admin/insights/agent-behaviour' },
  { id: 'logs', label: 'Log analytics', href: '/admin/insights/logs' }
];

export class InsightsNavigation {
  constructor(private readonly pathname: () => string) {}
  get configuration(): boolean { return this.pathname() === '/admin/insights/agent-behaviour/configuration'; }
  get activeId(): 'behaviour' | 'logs' { return this.pathname() === '/admin/insights/logs' ? 'logs' : 'behaviour'; }
}
