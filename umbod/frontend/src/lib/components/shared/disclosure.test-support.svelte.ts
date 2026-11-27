export function openFromParentEffect(open: () => void): () => void {
  return $effect.root((): void => {
    $effect((): void => open());
  });
}
