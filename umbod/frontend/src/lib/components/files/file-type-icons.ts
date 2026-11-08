export type FileIconKind = 'file' | 'folder' | 'image' | 'audio' | 'video' | 'pdf' | 'document' | 'spreadsheet' | 'presentation' | 'text' | 'code' | 'archive';

export interface FileIconDefinition {
  readonly kind: FileIconKind;
  readonly label: string;
  readonly paths: readonly string[];
}

interface FileFormatGroup {
  readonly icon: FileIconDefinition;
  readonly extensions: readonly string[];
  readonly contentTypes: readonly string[];
}

const fileOutline = 'M6 3h8l4 4v14H6zM14 3v5h4';
const genericFile: FileIconDefinition = { kind: 'file', label: 'File', paths: [fileOutline] };
const folder: FileIconDefinition = { kind: 'folder', label: 'Folder', paths: ['M3 6h7l2 3h9v11H3z'] };
const textFile: FileIconDefinition = { kind: 'text', label: 'Text file', paths: [fileOutline, 'M9 11h6M9 14h6M9 17h6'] };

const formatGroups: readonly FileFormatGroup[] = [
  {
    icon: { kind: 'image', label: 'Image file', paths: ['M3 3h18v18H3zM3 17l6-6 4 4 3-3 5 5M8 7h.01'] },
    extensions: ['jpg', 'jpeg', 'png', 'gif', 'webp', 'avif', 'svg', 'bmp', 'tif', 'tiff', 'heic', 'heif', 'ico', 'raw', 'dng', 'psd'],
    contentTypes: ['image/vnd.adobe.photoshop']
  },
  {
    icon: { kind: 'audio', label: 'Audio file', paths: ['M9 18V5l11-2v13M9 8l11-2M9 18a3 3 0 1 1-3-3c1.7 0 3 1.3 3 3M20 16a3 3 0 1 1-3-3c1.7 0 3 1.3 3 3'] },
    extensions: ['mp3', 'wav', 'flac', 'aac', 'm4a', 'ogg', 'oga', 'opus', 'aiff', 'aif', 'wma', 'mid', 'midi'],
    contentTypes: ['application/ogg']
  },
  {
    icon: { kind: 'video', label: 'Video file', paths: ['M3 5h18v14H3zM10 9l5 3-5 3z'] },
    extensions: ['mp4', 'mov', 'm4v', 'webm', 'mkv', 'avi', 'wmv', 'mpeg', 'mpg', 'ogv', '3gp'],
    contentTypes: []
  },
  {
    icon: { kind: 'pdf', label: 'PDF file', paths: [fileOutline, 'M8 17l3-7 2 5 3 2M8 17l8-2'] },
    extensions: ['pdf'],
    contentTypes: ['application/pdf']
  },
  {
    icon: { kind: 'document', label: 'Document file', paths: [fileOutline, 'M9 12h6M9 15h6M9 18h4'] },
    extensions: ['doc', 'docx', 'odt', 'rtf', 'pages', 'epub'],
    contentTypes: ['application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/vnd.oasis.opendocument.text', 'application/rtf', 'text/rtf', 'application/epub+zip', 'application/vnd.apple.pages']
  },
  {
    icon: { kind: 'spreadsheet', label: 'Spreadsheet file', paths: ['M3 3h18v18H3zM3 9h18M3 15h18M9 3v18'] },
    extensions: ['xls', 'xlsx', 'xlsm', 'ods', 'csv', 'tsv', 'numbers'],
    contentTypes: ['application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.ms-excel.sheet.macroenabled.12', 'application/vnd.oasis.opendocument.spreadsheet', 'text/csv', 'text/tab-separated-values', 'application/vnd.apple.numbers']
  },
  {
    icon: { kind: 'presentation', label: 'Presentation file', paths: ['M3 3h18M4 3v13h16V3M12 16v5M8 21l4-3 4 3M8 12V9M12 12V7M16 12V5'] },
    extensions: ['ppt', 'pptx', 'odp', 'key'],
    contentTypes: ['application/vnd.ms-powerpoint', 'application/vnd.openxmlformats-officedocument.presentationml.presentation', 'application/vnd.oasis.opendocument.presentation', 'application/vnd.apple.keynote']
  },
  {
    icon: textFile,
    extensions: ['txt', 'md', 'markdown', 'rst', 'log', 'tex'],
    contentTypes: ['text/plain', 'text/markdown', 'text/x-rst', 'application/x-tex']
  },
  {
    icon: { kind: 'code', label: 'Code file', paths: ['M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16'] },
    extensions: ['js', 'mjs', 'cjs', 'jsx', 'ts', 'tsx', 'svelte', 'vue', 'html', 'htm', 'css', 'scss', 'sass', 'less', 'py', 'ipynb', 'rb', 'php', 'java', 'kt', 'swift', 'go', 'rs', 'c', 'h', 'cpp', 'hpp', 'cs', 'sh', 'bash', 'zsh', 'ps1', 'sql', 'json', 'jsonl', 'xml', 'yaml', 'yml', 'toml', 'ini', 'conf'],
    contentTypes: ['application/json', 'application/ld+json', 'application/xml', 'text/xml', 'application/javascript', 'text/javascript', 'text/typescript', 'text/html', 'text/css', 'text/x-python', 'application/x-python-code', 'application/x-sh', 'text/x-shellscript', 'application/sql', 'application/yaml', 'text/yaml', 'application/toml']
  },
  {
    icon: { kind: 'archive', label: 'Archive file', paths: [fileOutline, 'M11 3v2m0 2v2m0 2v2M10 15h3v3h-3z'] },
    extensions: ['zip', '7z', 'rar', 'tar', 'gz', 'tgz', 'bz2', 'tbz2', 'xz', 'txz', 'zst', 'iso', 'dmg'],
    contentTypes: ['application/zip', 'application/x-zip-compressed', 'application/x-7z-compressed', 'application/vnd.rar', 'application/x-rar-compressed', 'application/x-tar', 'application/gzip', 'application/x-gzip', 'application/x-bzip2', 'application/x-xz', 'application/zstd', 'application/x-iso9660-image', 'application/x-apple-diskimage']
  }
];

const extensionIcons = new Map(formatGroups.flatMap(({ icon, extensions }) => extensions.map((extension): [string, FileIconDefinition] => [extension, icon])));
const contentTypeIcons = new Map(formatGroups.flatMap(({ icon, contentTypes }) => contentTypes.map((contentType): [string, FileIconDefinition] => [contentType, icon])));
const mediaIcons = new Map(formatGroups.filter(({ icon }) => ['image', 'audio', 'video'].includes(icon.kind)).map(({ icon }): [string, FileIconDefinition] => [icon.kind, icon]));

export function fileTypeIcon(kind: 'file' | 'directory', name: string, contentType: unknown): FileIconDefinition {
  if (kind === 'directory') return folder;
  const normalizedContentType = typeof contentType === 'string' ? contentType.split(';', 1)[0].trim().toLowerCase() : '';
  const mediaType = normalizedContentType.match(/^(image|audio|video)\/[^/\s]+$/u)?.[1] ?? '';
  const contentTypeIcon = contentTypeIcons.get(normalizedContentType) ?? mediaIcons.get(mediaType);
  if (contentTypeIcon && normalizedContentType !== 'text/plain') return contentTypeIcon;
  const normalizedName = name.trim().toLowerCase();
  const extensionIndex = normalizedName.lastIndexOf('.');
  const extensionIcon = extensionIndex > 0 ? extensionIcons.get(normalizedName.slice(extensionIndex + 1)) : undefined;
  return extensionIcon ?? contentTypeIcon ?? (normalizedContentType.startsWith('text/') ? textFile : genericFile);
}
