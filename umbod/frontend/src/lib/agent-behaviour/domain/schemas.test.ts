import { expect, test } from 'vitest';
import { configurationSchema, conflictSchema, patternSchema, publishSchema } from './schemas';

const pattern = { id: 'fallback', name: 'Fallback', description: 'Description', assessment_prompt: 'Assess', inclusion_criteria: '', exclusion_criteria: '', categories: ['quality'], polarity: 'negative', enabled: true };

test('enforces Unicode character bounds and preserves internal whitespace', (): void => {
  expect(patternSchema.parse({ ...pattern, name: '😀'.repeat(120), assessment_prompt: '  First\n  second  ' }).assessment_prompt).toBe('First\n  second');
  expect(patternSchema.safeParse({ ...pattern, name: '😀'.repeat(121) }).success).toBe(false);
  expect(patternSchema.safeParse({ ...pattern, assessment_prompt: '   ' }).success).toBe(false);
});

test('requires a boolean reporting setting on configuration, publication and conflicts', (): void => {
  const collections = { patterns: [], playbooks: [] };
  const configuration = { revision: 1, ...collections };
  const publication = { expected_revision: 1, ...collections };
  const conflict = { detail: { code: 'revision_conflict', current: configuration } };
  expect(configurationSchema.safeParse(configuration).success).toBe(false);
  expect(publishSchema.safeParse(publication).success).toBe(false);
  expect(conflictSchema.safeParse(conflict).success).toBe(false);
  expect(configurationSchema.safeParse({ ...configuration, reporting_enabled: 'false' }).success).toBe(false);
  expect(conflictSchema.parse({ detail: { ...conflict.detail, current: { ...configuration, reporting_enabled: false } } }).detail.current.reporting_enabled).toBe(false);
});

test('rejects the legacy per-playbook reporting permission', (): void => {
  const playbook = { id: 'review', name: 'Review', collection_instructions: 'Collect', pattern_ids: ['fallback'], enabled: true, allow_proactive: true };
  expect(publishSchema.safeParse({ expected_revision: 1, reporting_enabled: true, patterns: [pattern], playbooks: [playbook] }).success).toBe(false);
});

test('rejects duplicate IDs and duplicate categories while retaining reference shape validation', (): void => {
  expect(patternSchema.safeParse({ ...pattern, categories: ['quality', 'quality'] }).success).toBe(false);
  expect(publishSchema.safeParse({ expected_revision: 0, reporting_enabled: false, patterns: [{ ...pattern, enabled: false }], playbooks: [{ id: 'review', name: 'Review', collection_instructions: 'Collect', pattern_ids: ['fallback', 'retired'], enabled: true }] }).success).toBe(true);
  expect(publishSchema.safeParse({ expected_revision: 0, reporting_enabled: false, patterns: [], playbooks: [{ id: 'review', name: 'Review', collection_instructions: 'Collect', pattern_ids: [], enabled: false }] }).success).toBe(false);
  expect(publishSchema.safeParse({ expected_revision: 0, reporting_enabled: false, patterns: [pattern, pattern], playbooks: [] }).success).toBe(false);
  expect(publishSchema.safeParse({ expected_revision: 0, reporting_enabled: false, patterns: [], playbooks: [{ id: 'review', name: 'Review', collection_instructions: 'Collect', pattern_ids: ['INVALID'], enabled: false }] }).success).toBe(false);
});
