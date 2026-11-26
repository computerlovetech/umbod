import type { HeaderAccountIdentityState } from '#lib/header/accountIdentity.js';
import type { Configuration } from '#lib/agent-behaviour/domain/schemas.js';

export function configuration(): Configuration {
  return { revision: 1, reporting_enabled: true, patterns: [{ id: 'missing-context', name: 'Missing context', description: 'Required context is unavailable.', assessment_prompt: 'Assess unavailable context.', inclusion_criteria: '', exclusion_criteria: '', categories: [], polarity: 'negative', enabled: true }], playbooks: [{ id: 'diagnostics', name: 'Diagnostic reporting', collection_instructions: 'Report factual evidence only.', pattern_ids: ['missing-context'], enabled: true }] };
}

export class InsightsHarnessState {
  pathname: string;
  identity = $state<HeaderAccountIdentityState>({ kind: 'visible', name: 'Administrator', email: null, picture: null, hiddenValues: { id: 'account-a' } });

  constructor(pathname: string = '/admin/insights/agent-behaviour') {
    this.pathname = $state(pathname);
  }

  navigate = (event: MouseEvent): void => {
    if (!(event.target instanceof Element)) return;
    const link = event.target.closest<HTMLAnchorElement>('a');
    if (!link || !(link.pathname === '/admin/agent-diagnostics' || link.pathname.startsWith('/admin/insights/'))) return;
    event.preventDefault();
    this.pathname = link.pathname;
  };

  changeIdentity = (id: string): void => {
    this.identity = { kind: 'visible', name: 'Administrator', email: null, picture: null, hiddenValues: { id } };
  };

  hideIdentity = (): void => { this.identity = { kind: 'hidden' }; };
}
