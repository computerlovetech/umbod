export const descriptionPreviewLimit = 120;

export function descriptionPreview(description: string): string {
  const characters = Array.from(description.replace(/\s+/gu, ' ').trim());
  return characters.length > descriptionPreviewLimit ? characters.slice(0, descriptionPreviewLimit - 1).join('') + '…' : characters.join('');
}
