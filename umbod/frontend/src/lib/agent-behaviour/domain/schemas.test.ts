import { expect, test } from 'vitest';
import { patternSchema, publishSchema } from './schemas';

const pattern = { id: 'fallback', name: 'Fallback', description: 'Description', assessment_prompt: 'Assess', inclusion_criteria: '', exclusion_criteria: '', categories: ['quality'], polarity: 'negative', enabled: true };

test('enforces Unicode character bounds and preserves internal whitespace', (): void => {
  expect(patternSchema.parse({ ...pattern, name: '😀'.repeat(120), assessment_prompt: '  First\n  second  ' }).assessment_prompt).toBe('First\n  second');
  expect(patternSchema.safeParse({ ...pattern, name: '😀'.repeat(121) }).success).toBe(false);
  expect(patternSchema.safeParse({ ...pattern, assessment_prompt: '   ' }).success).toBe(false);
});

test('rejects duplicate IDs and duplicate categories while retaining reference shape validation', (): void => {
  expect(patternSchema.safeParse({ ...pattern, categories: ['quality', 'quality'] }).success).toBe(false);
  expect(publishSchema.safeParse({ expected_revision: 0, patterns: [{ ...pattern, enabled: false }], playbooks: [{ id: 'review', name: 'Review', collection_instructions: 'Collect', pattern_ids: ['fallback', 'retired'], enabled: true, allow_proactive: false }] }).success).toBe(true);
  expect(publishSchema.safeParse({ expected_revision: 0, patterns: [], playbooks: [{ id: 'review', name: 'Review', collection_instructions: 'Collect', pattern_ids: [], enabled: false, allow_proactive: false }] }).success).toBe(false);
  expect(publishSchema.safeParse({ expected_revision: 0, patterns: [pattern, pattern], playbooks: [] }).success).toBe(false);
  expect(publishSchema.safeParse({ expected_revision: 0, patterns: [], playbooks: [{ id: 'review', name: 'Review', collection_instructions: 'Collect', pattern_ids: ['INVALID'], enabled: false, allow_proactive: false }] }).success).toBe(false);
});
