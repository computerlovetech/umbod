import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
import type { Configuration } from '$lib/agent-behaviour/domain/schemas';

export function configuration(): Configuration {
  return { revision: 1, patterns: [{ id: 'missing-context', name: 'Missing context', description: 'Required context is unavailable.', assessment_prompt: 'Assess unavailable context.', inclusion_criteria: '', exclusion_criteria: '', categories: [], polarity: 'negative', enabled: true }], playbooks: [{ id: 'diagnostics', name: 'Diagnostic reporting', collection_instructions: 'Report factual evidence only.', pattern_ids: ['missing-context'], enabled: true, allow_proactive: false }] };
}

export class InsightsHarnessState {
  pathname = $state('/admin/insights/agent-behaviour/configuration');
  identity = $state<HeaderAccountIdentityState>({ kind: 'visible', name: 'Administrator', email: null, picture: null, hiddenValues: { id: 'account-a' } });

  navigate = (event: MouseEvent): void => {
    if (!(event.target instanceof Element)) return;
    const link = event.target.closest<HTMLAnchorElement>('a');
    if (!link || !link.pathname.startsWith('/admin/insights')) return;
    event.preventDefault();
    this.pathname = link.pathname;
  };

  changeIdentity = (id: string): void => {
    this.identity = { kind: 'visible', name: 'Administrator', email: null, picture: null, hiddenValues: { id } };
  };

  hideIdentity = (): void => { this.identity = { kind: 'hidden' }; };
}
