import { describe, expect, test } from 'vitest';
import { load } from './+page';

describe('workspace entry', () => {
  test('root redirects temporarily to the dashboard', async (): Promise<void> => {
    await expect(async () => load({} as never)).rejects.toMatchObject({ status: 307, location: '/dashboard' });
  });
});
