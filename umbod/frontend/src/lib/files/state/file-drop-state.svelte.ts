export class FileDropState {
  active = $state(false);
  private depth = 0;

  constructor(
    private readonly select: (files: readonly File[]) => void,
    private readonly reject: (message: string) => void,
    private readonly disabled: () => boolean
  ) {}

  preventOutside = (event: DragEvent): void => {
    if (!this.hasFiles(event) || event.defaultPrevented) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'none';
    this.reset();
  };

  enter = (event: DragEvent): void => {
    if (!this.hasFiles(event) || this.disabled()) return;
    event.preventDefault();
    ++this.depth;
    this.active = true;
  };

  over = (event: DragEvent): void => {
    if (!this.hasFiles(event)) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = this.disabled() ? 'none' : 'copy';
  };

  leave = (): void => {
    this.depth = Math.max(0, this.depth - 1);
    if (this.depth === 0) this.active = false;
  };

  drop = (event: DragEvent): void => {
    this.reset();
    if (!this.hasFiles(event)) return;
    event.preventDefault();
    if (this.disabled() || !event.dataTransfer) return;
    const items = Array.from(event.dataTransfer.items).filter((item) => item.kind === 'file');
    if (items.some((item) => typeof item.webkitGetAsEntry === 'function' && item.webkitGetAsEntry()?.isDirectory)) {
      this.reject('Folders cannot be uploaded. Choose a single file instead.');
      return;
    }
    const files = Array.from(event.dataTransfer.files);
    if (items.length > 1 || files.length > 1) {
      this.reject('Choose one file at a time. Multiple files were not selected.');
      return;
    }
    if (files.length === 0) {
      this.reject('This file could not be read. Try choosing it with the file picker.');
      return;
    }
    this.select(files);
  };

  private hasFiles(event: DragEvent): boolean {
    return !!event.dataTransfer && Array.from(event.dataTransfer.types).includes('Files');
  }

  reset = (): void => {
    this.depth = 0;
    this.active = false;
  };
}
