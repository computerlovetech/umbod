import type { z } from 'zod';
import type { Configuration } from './schemas';

const guidance: Record<string, string> = {
  name: 'Add a name of up to 120 characters.',
  description: 'Describe what the agent should notice in up to 2,000 characters.',
  assessment_prompt: 'Use an assessment prompt of up to 4,000 characters.',
  inclusion_criteria: 'Keep when it counts within 4,000 characters.',
  exclusion_criteria: 'Keep when it does not count within 4,000 characters.',
  categories: 'Use up to 10 unique lowercase category labels, starting with a letter and using only letters, numbers or hyphens.',
  polarity: 'Choose positive, negative or neutral polarity.',
  collection_instructions: 'Add collection instructions of up to 8,000 characters.',
  pattern_ids: 'Keep between 1 and 20 unique configured pattern references.',
  patterns: 'Use no more than 50 patterns.',
  playbooks: 'Use no more than 20 reporting settings.'
};

function fieldFeedback(field: string): string {
  return guidance[field] ?? 'Check these settings before saving.';
}

export function newPatternFeedback(issues: readonly z.core.$ZodIssue[]): string {
  return [...new Set(issues.map((issue): string => fieldFeedback(String(issue.path[0]))))].join(' ');
}

export function configurationFeedback(issues: readonly z.core.$ZodIssue[], configuration: Configuration): string {
  return [...new Set(issues.map((issue): string => {
    const collection = issue.path[0];
    const index = issue.path[1];
    const item = typeof index === 'number' && (collection === 'patterns' || collection === 'playbooks') ? configuration[collection][index] : undefined;
    const name = item?.name || (collection === 'patterns' ? 'New pattern' : 'Reporting settings');
    const field = String(issue.path[2] ?? collection);
    return `${name}: ${fieldFeedback(field)}`;
  }))].join(' ');
}
