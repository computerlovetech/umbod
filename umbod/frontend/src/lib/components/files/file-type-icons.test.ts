import { describe, expect, test } from 'vitest';
import { fileTypeIcon, type FileIconKind } from './file-type-icons';

const extensionGroups: readonly { kind: FileIconKind; extensions: readonly string[] }[] = [
  { kind: 'image', extensions: ['jpg', 'jpeg', 'png', 'gif', 'webp', 'avif', 'svg', 'heic', 'tiff', 'psd'] },
  { kind: 'audio', extensions: ['mp3', 'wav', 'flac', 'm4a', 'ogg', 'opus', 'midi'] },
  { kind: 'video', extensions: ['mp4', 'mov', 'webm', 'mkv', 'avi'] },
  { kind: 'pdf', extensions: ['pdf'] },
  { kind: 'document', extensions: ['doc', 'docx', 'odt', 'rtf', 'pages', 'epub'] },
  { kind: 'spreadsheet', extensions: ['xls', 'xlsx', 'xlsm', 'ods', 'csv', 'tsv', 'numbers'] },
  { kind: 'presentation', extensions: ['ppt', 'pptx', 'odp', 'key'] },
  { kind: 'text', extensions: ['txt', 'md', 'markdown', 'rst', 'log', 'tex'] },
  { kind: 'code', extensions: ['js', 'ts', 'tsx', 'svelte', 'py', 'html', 'css', 'go', 'rs', 'java', 'sh', 'sql', 'json', 'xml', 'yaml', 'toml'] },
  { kind: 'archive', extensions: ['zip', '7z', 'rar', 'tar', 'gz', 'tgz', 'bz2', 'xz', 'zst', 'dmg'] }
];

describe('file format icon mapping', (): void => {
  test.each(extensionGroups)('$kind formats share the same icon regardless of extension casing', ({ kind, extensions }): void => {
    const icon = fileTypeIcon('file', 'report.' + extensions[0], {});
    expect(icon.kind).toBe(kind);
    for (const extension of extensions) {
      expect(fileTypeIcon('file', 'report.' + extension, {})).toBe(icon);
      expect(fileTypeIcon('file', 'report.' + extension.toUpperCase(), 'application/octet-stream')).toBe(icon);
    }
  });

  test.each([
    ['image/jpeg', 'image'], ['image/svg+xml', 'image'], ['image/future-format', 'image'],
    ['audio/mpeg', 'audio'], ['video/mp4', 'video'], ['application/pdf', 'pdf'],
    ['application/msword', 'document'], ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'document'],
    ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'spreadsheet'], ['text/csv', 'spreadsheet'],
    ['application/vnd.openxmlformats-officedocument.presentationml.presentation', 'presentation'],
    ['text/plain', 'text'], ['text/calendar', 'text'], ['application/json', 'code'], ['text/html', 'code'],
    ['application/zip', 'archive'], ['application/gzip', 'archive']
  ])('uses %s when the filename has no known extension', (contentType, expected): void => {
    expect(fileTypeIcon('file', 'download', contentType).kind).toBe(expected);
  });

  test('normalizes MIME casing, whitespace and parameters', (): void => {
    expect(fileTypeIcon('file', 'download', ' IMAGE/PNG ; charset=binary').kind).toBe('image');
  });

  test('recognized specific MIME types take precedence over conflicting extensions', (): void => {
    expect(fileTypeIcon('file', 'notes.txt', 'image/png').kind).toBe('image');
    expect(fileTypeIcon('file', 'data.zip', 'application/epub+zip').kind).toBe('document');
  });

  test.each(['text/plain', 'application/octet-stream', 'application/unknown', '', {}])('extensions refine nonspecific content type %j', (contentType): void => {
    expect(fileTypeIcon('file', 'script.py', contentType).kind).toBe('code');
    expect(fileTypeIcon('file', 'backup.tar.gz', contentType).kind).toBe('archive');
  });

  test.each(['', 'README', '.png', 'report.', 'report.unknown', 'photo.jpg.exe'])('unknown or absent format in %j retains the generic file icon', (name): void => {
    expect(fileTypeIcon('file', name, {}).kind).toBe('file');
  });

  test.each([{}, undefined, null, 42, 'image', 'image/', 'application/octet-stream'])('unspecified or invalid MIME %j safely falls back', (contentType): void => {
    expect(fileTypeIcon('file', 'download', contentType).kind).toBe('file');
  });

  test('home is an explicit presentation kind rather than a name inference', (): void => {
    expect(fileTypeIcon('home', 'Renamed storage', {}).kind).toBe('home');
    expect(fileTypeIcon('home', 'Renamed storage', {}).label).toBe('Home folder');
    expect(fileTypeIcon('directory', 'Home-internal-identity', {}).kind).toBe('folder');
  });

  test('a directory is always a folder even when its name and MIME resemble a file', (): void => {
    expect(fileTypeIcon('directory', 'photos.zip', 'application/pdf').kind).toBe('folder');
  });
});
