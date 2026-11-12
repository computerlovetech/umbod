export class FileThumbnailState {
  private failedFile = $state.raw<File | undefined>(undefined);

  constructor(private readonly file: () => File | undefined) {}

  get visible(): boolean {
    const file = this.file();
    return !!file && /^image\/(png|jpeg|gif|webp|avif|bmp)$/i.test(file.type) && file !== this.failedFile;
  }

  attach = (image: HTMLImageElement): (() => void) | undefined => {
    const file = this.file();
    if (!file) return;
    const url = URL.createObjectURL(file);
    image.src = url;
    const fail = (): void => { this.failedFile = file; };
    image.addEventListener('error', fail);
    return (): void => {
      image.removeEventListener('error', fail);
      URL.revokeObjectURL(url);
    };
  };
}
