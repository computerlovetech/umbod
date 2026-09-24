import { isOperationalError } from './infrastructure/transport';

export type SelectedDetailResult<Detail> =
  | { selectedId: undefined }
  | { selectedId: string; selectedDetail: Detail }
  | { selectedId: string; selectedDetailFailed: true };

export type LoadSelectedDetailOptions<Summary, Detail> = {
  summaries: readonly Summary[];
  requestedId: string | null;
  idOf: (summary: Summary) => string;
  loadDetail: (id: string) => Promise<Detail>;
  eligible?: (summary: Summary) => boolean;
};

export async function loadSelectedDetail<Summary, Detail>({
  summaries,
  requestedId,
  idOf,
  loadDetail,
  eligible = (): boolean => true
}: LoadSelectedDetailOptions<Summary, Detail>): Promise<SelectedDetailResult<Detail>> {
  const eligibleSummaries = summaries.filter(eligible);
  const selected = eligibleSummaries.find((summary) => idOf(summary) === requestedId) ?? eligibleSummaries[0];
  if (selected === undefined) return { selectedId: undefined };
  const selectedId = idOf(selected);
  try {
    return { selectedId, selectedDetail: await loadDetail(selectedId) };
  } catch (error) {
    if (!isOperationalError(error)) throw error;
    return { selectedId, selectedDetailFailed: true };
  }
}
