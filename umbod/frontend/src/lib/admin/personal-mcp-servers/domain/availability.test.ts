import { describe, expect, test } from 'vitest';
import { configurationFixture } from '../availability.test-support';
import { personalServerAvailability } from './availability';

describe('resolved personal connections availability', () => {
  test.each([true, false])('projects resolved registration %s independently of OAuth', (enabled) => {
    expect(personalServerAvailability(configurationFixture(enabled, false))).toEqual({ registration: enabled ? 'enabled' : 'disabled', authorization: 'disabled' });
  });
  test('missing group and duplicate groups fail closed', () => {
    expect(personalServerAvailability({ groups: [] })).toEqual({ registration: 'unknown', authorization: 'unknown' });
    const configuration = configurationFixture();
    configuration.groups.push(configuration.groups[0]);
    expect(personalServerAvailability(configuration)).toEqual({ registration: 'unknown', authorization: 'unknown' });
  });
  test.each(['missing', 'duplicate', 'mistyped'] as const)('%s registration entry is unknown, not inferred from OAuth', (mode) => {
    const configuration = configurationFixture();
    const entries = configuration.groups[0].entries;
    if (mode === 'missing') entries.shift();
    if (mode === 'duplicate') entries.push(entries[0]);
    if (mode === 'mistyped') entries[0] = { ...entries[0], type: 'string', value: 'true' };
    expect(personalServerAvailability(configuration)).toEqual({ registration: 'unknown', authorization: 'enabled' });
  });
  test.each(['missing', 'duplicate', 'mistyped'] as const)('%s OAuth entry does not disable confirmed registration', (mode) => {
    const configuration = configurationFixture();
    const entries = configuration.groups[0].entries;
    if (mode === 'missing') entries.pop();
    if (mode === 'duplicate') entries.push(entries[1]);
    if (mode === 'mistyped') entries[1] = { ...entries[1], type: 'string', value: 'false' };
    expect(personalServerAvailability(configuration)).toEqual({ registration: 'enabled', authorization: 'unknown' });
  });
});
