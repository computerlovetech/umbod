import { describe, expect, test } from 'vitest';
import { DownstreamMcpPromptCatalogState } from './downstream-mcp-prompt-catalog-state.svelte';

describe('DownstreamMcpPromptCatalogState', () => {
  test('toggle creates dirty payload and finishSave clears dirty', () => {
    const state = new DownstreamMcpPromptCatalogState({
      prompts: [
        {
          name: 'summarize',
          description: 'Summarize',
          arguments: [],
          activation_status: 'disabled'
        }
      ],
      available_actions: ['activate']
    });

    state.setPromptActivation('summarize', true);
    expect(state.dirty).toBe(true);
    expect(JSON.parse(state.activationRequestJson())).toEqual([
      { prompt_id: 'summarize', activation_status: 'enabled' }
    ]);

    state.finishSave({
      connector_id: 'c1',
      prompts: [{ prompt_id: 'summarize', activation_status: 'enabled' }]
    });
    expect(state.dirty).toBe(false);
  });
});
