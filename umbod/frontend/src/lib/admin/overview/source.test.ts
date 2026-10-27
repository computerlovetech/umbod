import { describe, expect, test } from 'vitest';
import { InMemoryOverviewSource } from './in-memory-source';
import { overviewFixture } from './fixtures.test-support';
import { unavailableOverview } from './models';
import type { OverviewSource } from './port';

describe('overview summary port', () => {
  test('loads validated summaries including zero, populated and unavailable counts', async () => {
    for (const overview of [overviewFixture(), overviewFixture(500), unavailableOverview()]) {
      const source: OverviewSource = new InMemoryOverviewSource(overview);
      expect(await source.load()).toEqual(overview);
    }
  });

  test('rejects malformed in-memory summaries', async () => {
    const overview = overviewFixture();
    overview.permissionGroups = { status: 'available', value: -1 };
    const source: OverviewSource = new InMemoryOverviewSource(overview);
    await expect(source.load()).rejects.toThrow();
  });
});
