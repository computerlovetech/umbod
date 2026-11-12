import { prepareCsvPreview, type CsvPreview } from './csv';

export class CsvPreviewState {
  private readonly currentPreview = $derived.by((): CsvPreview => prepareCsvPreview(this.content()));

  constructor(private readonly content: () => string) {}

  get preview(): CsvPreview { return this.currentPreview; }
}
