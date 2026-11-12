import { expect, test } from 'vitest';
import { filesystemNode } from '$lib/files/fixtures.test-support';
import { InMemoryFileContent } from '$lib/files/preview/in-memory-content.test-support';
import { PreviewReadError } from '$lib/files/preview/ports';
import { imagePreviewAdapter } from './image-adapter';

test.each<[string, string | undefined, boolean]>([
  ['picture', 'image/png', true],
  ['picture.txt', ' IMAGE/JPEG ; charset=binary', true],
  ['picture.svg', 'image/gif', true],
  ['picture', 'image/webp', true],
  ['picture', 'image/bmp', true],
  ['PICTURE.PNG', undefined, true],
  ['picture.jpg', '', true],
  ['picture.jpeg', '  ', true],
  ['picture.jpe', undefined, true],
  ['picture.gif', 'APPLICATION/OCTET-STREAM; charset=binary', true],
  ['picture.webp', undefined, true],
  ['picture.bmp', undefined, true],
  ['picture.png', 'image/svg+xml', false],
  ['picture.jpg', 'text/plain', false],
  ['picture.gif', 'text/html', false],
  ['picture.webp', 'application/json', false],
  ['picture.png', 'image/unknown', false],
  ['picture.png', 'image/*', false],
  ['picture.png', 'image/heic', false],
  ['picture.png', 'image/tiff', false],
  ['picture.png', 'image/avif', false],
  ['picture.svg', 'image/svg+xml', false],
  ['picture.svg', undefined, false],
  ['picture.svgz', 'application/octet-stream', false],
  ['picture.heic', undefined, false],
  ['picture.heif', undefined, false],
  ['picture.tif', undefined, false],
  ['picture.tiff', undefined, false],
  ['picture.avif', undefined, false],
  ['picture.png.svg', undefined, false],
  ['png', undefined, false],
  ['picture', undefined, false]
])('selects %s with MIME %s as an image: %s', (name: string, mime: string | undefined, supported: boolean): void => {
  const file = filesystemNode({ name, kind: 'file', metadata: { content_type: mime ?? {}, attributes: {} } });
  expect(imagePreviewAdapter.supports(file)).toBe(supported);
});

interface RasterFixture {
  readonly name: string;
  readonly mime: string;
  readonly signature: readonly number[];
}

const rasterFixtures: readonly RasterFixture[] = [
  { name: 'PNG', mime: 'image/png', signature: [137, 80, 78, 71, 13, 10, 26, 10] },
  { name: 'JPEG', mime: 'image/jpeg', signature: [255, 216, 255] },
  { name: 'GIF87a', mime: 'image/gif', signature: [71, 73, 70, 56, 55, 97] },
  { name: 'GIF89a', mime: 'image/gif', signature: [71, 73, 70, 56, 57, 97] },
  { name: 'WebP', mime: 'image/webp', signature: [82, 73, 70, 70, 4, 0, 0, 0, 87, 69, 66, 80] },
  { name: 'BMP', mime: 'image/bmp', signature: [66, 77] }
];

test.each(rasterFixtures)('preserves binary $name bytes under the detected MIME', async ({ mime, signature }: RasterFixture): Promise<void> => {
  const bytes = new Uint8Array([...signature, 0, 128, 255, 195, 40]);
  const source = new InMemoryFileContent(async (): Promise<Uint8Array> => bytes);
  const signal = new AbortController().signal;
  const content = await imagePreviewAdapter.read(source, 'image-file', signal);
  const prefix = 'data:' + mime + ';base64,';
  expect(content.startsWith(prefix)).toBe(true);
  expect(Uint8Array.from(atob(content.slice(prefix.length)), (character: string): number => character.charCodeAt(0))).toEqual(bytes);
  expect(source.requests).toEqual([{ id: 'image-file', signal }]);
});

test('keeps zero-byte content empty for the preview container', async (): Promise<void> => {
  const source = new InMemoryFileContent(async (): Promise<Uint8Array> => new Uint8Array());
  expect(await imagePreviewAdapter.read(source, 'empty-image', new AbortController().signal)).toBe('');
});

test.each<[string, readonly number[]]>([
  ['truncated PNG', [137, 80, 78, 71, 13, 10, 26]],
  ['invalid PNG suffix', [137, 80, 78, 71, 0, 0, 0, 0]],
  ['truncated JPEG', [255, 216]],
  ['truncated GIF', [71, 73, 70, 56, 57]],
  ['unknown GIF version', [71, 73, 70, 56, 56, 97]],
  ['truncated WebP', [82, 73, 70, 70, 0, 0, 0, 0, 87, 69, 66]],
  ['non-WebP RIFF', [82, 73, 70, 70, 0, 0, 0, 0, 87, 65, 86, 69]],
  ['WebP without RIFF', [0, 0, 0, 0, 0, 0, 0, 0, 87, 69, 66, 80]],
  ['truncated BMP', [66]],
  ['unknown binary', [0, 128, 255]],
  ['TIFF', [73, 73, 42, 0]],
  ['AVIF', [0, 0, 0, 24, 102, 116, 121, 112, 97, 118, 105, 102]]
])('rejects %s with a preview read error', async (_name: string, payload: readonly number[]): Promise<void> => {
  const source = new InMemoryFileContent(async (): Promise<Uint8Array> => new Uint8Array(payload));
  await expect(imagePreviewAdapter.read(source, 'invalid-image', new AbortController().signal)).rejects.toEqual(new PreviewReadError('error'));
});

test.each(['<svg xmlns="http://www.w3.org/2000/svg"></svg>', '<html><script>alert(1)</script></html>', 'data:image/png;base64,iVBORw0KGgo='])(
  'rejects text payload %s instead of embedding it', async (payload: string): Promise<void> => {
    const source = new InMemoryFileContent(async (): Promise<string> => payload);
    await expect(imagePreviewAdapter.read(source, 'text-image', new AbortController().signal)).rejects.toEqual(new PreviewReadError('error'));
  }
);

test('propagates content-source failures without converting them to image errors', async (): Promise<void> => {
  const failure = new PreviewReadError('denied');
  const source = new InMemoryFileContent(async (): Promise<Uint8Array> => { throw failure; });
  await expect(imagePreviewAdapter.read(source, 'denied-image', new AbortController().signal)).rejects.toBe(failure);
});

test('passes the original aborted signal to the binary source and propagates rejection', async (): Promise<void> => {
  const controller = new AbortController();
  const failure = new DOMException('Read aborted', 'AbortError');
  controller.abort(failure);
  const source = new InMemoryFileContent(async (_id: string, signal: AbortSignal): Promise<Uint8Array> => {
    signal.throwIfAborted();
    return new Uint8Array([66, 77]);
  });
  await expect(imagePreviewAdapter.read(source, 'cancelled-image', controller.signal)).rejects.toBe(failure);
  expect(source.requests).toEqual([{ id: 'cancelled-image', signal: controller.signal }]);
});
