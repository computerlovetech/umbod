type AdminFileUploadStateOptions = {
  accept?: string;
  maxBytes?: number;
};

export class AdminFileUploadState {
  selectedFileName = $state('');
  selectedFileSize = $state('');
  error = $state('');
  dragging = $state(false);

  select = (event: Event, options: AdminFileUploadStateOptions): void => {
    if (!(event.currentTarget instanceof HTMLInputElement)) return;
    this.applySelection(event.currentTarget, event.currentTarget.files, options);
  };

  dragOver = (event: DragEvent): void => {
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
    this.dragging = true;
  };

  dragLeave = (event: DragEvent): void => {
    if (!(event.currentTarget instanceof HTMLElement)) return;
    if (event.relatedTarget instanceof Node && event.currentTarget.contains(event.relatedTarget)) return;
    this.dragging = false;
  };

  drop = (event: DragEvent, options: AdminFileUploadStateOptions): void => {
    event.preventDefault();
    this.dragging = false;
    if (!(event.currentTarget instanceof HTMLElement) || !event.dataTransfer) return;
    const input = event.currentTarget.querySelector<HTMLInputElement>('input[type="file"]');
    if (!input) return;
    input.files = event.dataTransfer.files;
    this.applySelection(input, input.files, options);
  };

  remove = (event: Event): void => {
    if (!(event.currentTarget instanceof HTMLElement)) return;
    const upload = event.currentTarget.closest<HTMLElement>('[data-file-upload]');
    const input = upload?.querySelector<HTMLInputElement>('input[type="file"]');
    if (input) input.value = '';
    this.clearSelection();
  };

  private applySelection(input: HTMLInputElement, files: FileList | null, options: AdminFileUploadStateOptions): void {
    const file = files?.item(0);
    if (!file) {
      this.clearSelection();
      return;
    }
    const validationError = this.validate(file, options);
    if (validationError) {
      input.value = '';
      this.clearSelection();
      this.error = validationError;
      return;
    }
    this.selectedFileName = file.name;
    this.selectedFileSize = this.formatFileSize(file.size);
    this.error = '';
  }

  private validate(file: File, options: AdminFileUploadStateOptions): string {
    if (options.maxBytes !== undefined && file.size > options.maxBytes) {
      return `Choose a file smaller than ${this.formatFileSize(options.maxBytes)}.`;
    }
    if (!options.accept) return '';
    const accepted = options.accept.split(',').map((value) => value.trim().toLowerCase());
    const fileName = file.name.toLowerCase();
    const fileType = file.type.toLowerCase();
    const matches = accepted.some((value) => value.startsWith('.') ? fileName.endsWith(value) : value === fileType);
    return matches ? '' : 'Choose a supported file type.';
  }

  private clearSelection(): void {
    this.selectedFileName = '';
    this.selectedFileSize = '';
    this.error = '';
  }

  private formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
}
