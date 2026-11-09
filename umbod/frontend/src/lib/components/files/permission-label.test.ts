import { describe, expect, test } from 'vitest';
import { permissionLabel } from './permission-label';

describe('permission labels', (): void => {
  test.each([
    [true, true, false, false, false, 'Read only'],
    [false, true, false, false, false, 'Read only'],
    [true, true, true, false, false, 'Can edit'],
    [true, true, true, true, true, 'Can edit'],
    [true, false, false, false, false, 'Details only'],
    [false, false, false, false, false, 'Custom access'],
    [true, false, true, false, false, 'Custom access'],
    [true, true, false, true, false, 'Custom access'],
    [true, true, false, false, true, 'Custom access']
  ])('labels discover=%s read=%s write=%s delete=%s share=%s as %s', (can_discover, can_read, can_write, can_delete, can_share, expected): void => {
    expect(permissionLabel({ can_discover, can_read, can_write, can_delete, can_share })).toBe(expected);
  });
});
