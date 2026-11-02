import { describe, expect, test } from 'vitest';
import { descriptionPreview, descriptionPreviewLimit } from './row-presentation';

describe('file row description previews', (): void => {
  test('collapses whitespace into one trimmed line', (): void => {
    expect(descriptionPreview('  First line\n\tSecond line\r\nThird  ')).toBe('First line Second line Third');
    expect(descriptionPreview(' \n\t ')).toBe('');
  });

  test('preserves descriptions at the limit and includes ellipsis inside the character budget', (): void => {
    const description = 'a'.repeat(descriptionPreviewLimit);
    expect(descriptionPreview(description)).toBe(description);
    expect(descriptionPreview(description + 'b')).toBe('a'.repeat(descriptionPreviewLimit - 1) + '…');
  });

  test('does not split surrogate pairs when shortening Unicode descriptions', (): void => {
    const preview = descriptionPreview('😀'.repeat(descriptionPreviewLimit + 1));
    expect(Array.from(preview)).toHaveLength(descriptionPreviewLimit);
    expect(preview).toBe('😀'.repeat(descriptionPreviewLimit - 1) + '…');
  });
});
