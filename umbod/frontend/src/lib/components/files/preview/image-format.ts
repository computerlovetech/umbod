type RasterMime = 'image/png' | 'image/jpeg' | 'image/gif' | 'image/webp' | 'image/bmp';

interface SignaturePart {
  readonly offset: number;
  readonly bytes: readonly number[];
}

interface RasterFormat {
  readonly mime: RasterMime;
  readonly extensions: readonly string[];
  readonly signatures: readonly (readonly SignaturePart[])[];
}

const rasterFormats: readonly RasterFormat[] = [
  {
    mime: 'image/png', extensions: ['png'],
    signatures: [[{ offset: 0, bytes: [137, 80, 78, 71, 13, 10, 26, 10] }]]
  },
  {
    mime: 'image/jpeg', extensions: ['jpg', 'jpeg', 'jpe'],
    signatures: [[{ offset: 0, bytes: [255, 216, 255] }]]
  },
  {
    mime: 'image/gif', extensions: ['gif'],
    signatures: [
      [{ offset: 0, bytes: [71, 73, 70, 56, 55, 97] }],
      [{ offset: 0, bytes: [71, 73, 70, 56, 57, 97] }]
    ]
  },
  {
    mime: 'image/webp', extensions: ['webp'],
    signatures: [[{ offset: 0, bytes: [82, 73, 70, 70] }, { offset: 8, bytes: [87, 69, 66, 80] }]]
  },
  {
    mime: 'image/bmp', extensions: ['bmp'],
    signatures: [[{ offset: 0, bytes: [66, 77] }]]
  }
];

export function supportsRasterImage(name: string, contentType: string): boolean {
  const mime = contentType.split(';')[0].trim().toLowerCase();
  if (mime && mime !== 'application/octet-stream') {
    return rasterFormats.some((format: RasterFormat): boolean => format.mime === mime);
  }
  const extension = name.slice(name.lastIndexOf('.') + 1).toLowerCase();
  return name.includes('.') && rasterFormats.some((format: RasterFormat): boolean => format.extensions.includes(extension));
}

function matchesSignature(bytes: Uint8Array, signature: readonly SignaturePart[]): boolean {
  return signature.every((part: SignaturePart): boolean =>
    part.bytes.every((byte: number, index: number): boolean => bytes[part.offset + index] === byte)
  );
}

export function detectRasterMime(bytes: Uint8Array): RasterMime | undefined {
  return rasterFormats.find((format: RasterFormat): boolean =>
    format.signatures.some((signature: readonly SignaturePart[]): boolean => matchesSignature(bytes, signature))
  )?.mime;
}
