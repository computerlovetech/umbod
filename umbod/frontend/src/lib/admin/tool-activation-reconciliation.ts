export type PresentedSaveFailure = {
  status: number;
  data: Record<string, unknown>;
};

type SaveFailurePresentationOptions<TAuthoritative> = {
  originalError: unknown;
  presentOriginal: (error: unknown) => PresentedSaveFailure;
  loadAuthoritative: () => Promise<TAuthoritative>;
  presentAuthoritative: (response: TAuthoritative) => Record<string, unknown>;
};

export async function presentSaveFailureWithReconciliation<TAuthoritative>(
  options: SaveFailurePresentationOptions<TAuthoritative>
): Promise<PresentedSaveFailure> {
  const original = options.presentOriginal(options.originalError);
  try {
    const response = await options.loadAuthoritative();
    return { status: original.status, data: { ...original.data, ...options.presentAuthoritative(response) } };
  } catch {
    return original;
  }
}
