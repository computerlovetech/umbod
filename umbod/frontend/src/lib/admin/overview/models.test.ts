import { describe, expect, test } from 'vitest';
import { adminOverviewResponseSchema, availableSchema, connectorCountsSchema, toolCountsSchema, unavailableOverview } from './models';
import { overviewResponseFixture } from './fixtures.test-support';
import { z } from 'zod';

describe('overview wire schema', () => {
  test('accepts zero, populated and mixed availability without recomputing counts', () => {
    for (const count of [0, 999999]) {
      const response = overviewResponseFixture(count);
      response.breakdown[1].tools = { status: 'unavailable' };
      response.configured = { status: 'unavailable' };
      expect(adminOverviewResponseSchema.parse(response)).toEqual(response);
    }
    const { permissionGroups, ...overview } = unavailableOverview();
    expect(adminOverviewResponseSchema.parse({ ...overview, permission_groups: permissionGroups })).toEqual({ ...overview, permission_groups: permissionGroups });
  });

  test.each([-1, 0.5, NaN, Infinity, '1', null])('rejects invalid count %s in every count field', (count) => {
    const response = overviewResponseFixture();
    expect(adminOverviewResponseSchema.safeParse({ ...response, configured: { status: 'available', value: count } }).success).toBe(false);
    expect(adminOverviewResponseSchema.safeParse({ ...response, published: { status: 'available', value: count } }).success).toBe(false);
    expect(adminOverviewResponseSchema.safeParse({ ...response, permission_groups: { status: 'available', value: count } }).success).toBe(false);
    for (const field of Object.keys(connectorCountsSchema.shape)) {
      const counts = { configured: 0, published: 0, unconfigured: 0, draft: 0, unpublished: 0, unhealthy: 0, [field]: count };
      expect(connectorCountsSchema.safeParse(counts).success).toBe(false);
    }
    for (const field of Object.keys(toolCountsSchema.shape)) {
      expect(toolCountsSchema.safeParse({ enabled: 0, known: 0, [field]: count }).success).toBe(false);
    }
  });

  test.each([
    { status: 'available' },
    { status: 'available', value: null },
    { status: 'unavailable', value: 0 },
    { status: 'unknown' },
    null,
    0
  ])('rejects malformed availability %j', (value) => {
    expect(availableSchema(z.number()).safeParse(value).success).toBe(false);
  });

  test('requires all summary fields and snake case permission groups', () => {
    const response = overviewResponseFixture();
    for (const field of Object.keys(response)) {
      const incomplete: Record<string, unknown> = { ...response };
      delete incomplete[field];
      expect(adminOverviewResponseSchema.safeParse(incomplete).success).toBe(false);
    }
    const { permission_groups, ...rest } = response;
    expect(adminOverviewResponseSchema.safeParse({ ...rest, permissionGroups: permission_groups }).success).toBe(false);
  });

  test('requires exactly one breakdown per kind in contract order', () => {
    const response = overviewResponseFixture();
    const [catalog, openapi, mcp] = response.breakdown;
    for (const breakdown of [[], [catalog], [catalog, openapi], [catalog, openapi, mcp, mcp], [mcp, openapi, catalog], [catalog, catalog, mcp], [{ ...catalog, kind: 'other' }, openapi, mcp]]) {
      expect(adminOverviewResponseSchema.safeParse({ ...response, breakdown }).success).toBe(false);
    }
  });
});
