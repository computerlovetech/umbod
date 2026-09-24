import { describe, expect, it, vi } from 'vitest';
import { NetworkError } from './infrastructure/transport';
import { loadSelectedDetail } from './selected-detail-facade';

type Item = { id: string; eligible: boolean };
const items: Item[] = [{ id: 'a', eligible: false }, { id: 'b', eligible: true }, { id: 'c', eligible: true }];

function idOf(item: Item): string {
  return item.id;
}

describe('loadSelectedDetail', (): void => {
  it('uses a valid requested selection', async (): Promise<void> => {
    expect(await loadSelectedDetail({ summaries: items, requestedId: 'c', idOf, loadDetail: async (id) => id, eligible: (item) => item.eligible })).toEqual({ selectedId: 'c', selectedDetail: 'c' });
  });

  it('falls back to the first eligible selection', async (): Promise<void> => {
    expect(await loadSelectedDetail({ summaries: items, requestedId: 'missing', idOf, loadDetail: async (id) => id, eligible: (item) => item.eligible })).toEqual({ selectedId: 'b', selectedDetail: 'b' });
  });

  it('does not load without an eligible selection', async (): Promise<void> => {
    const loader = vi.fn(async (id: string): Promise<string> => id);
    expect(await loadSelectedDetail({ summaries: items, requestedId: null, idOf, loadDetail: loader, eligible: (): boolean => false })).toEqual({ selectedId: undefined });
    expect(loader).not.toHaveBeenCalled();
  });

  it('isolates detail failure while retaining selection', async (): Promise<void> => {
    const loadDetail = async (): Promise<string> => {
      throw new NetworkError(new Error('failed'));
    };
    expect(await loadSelectedDetail({ summaries: items, requestedId: 'b', idOf, loadDetail, eligible: (item) => item.eligible })).toEqual({ selectedId: 'b', selectedDetailFailed: true });
  });
});
