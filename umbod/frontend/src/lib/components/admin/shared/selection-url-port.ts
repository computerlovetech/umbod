export interface SelectionUrlPort {
  readSelection(): string | null;
  replaceSelection(selectionId: string): void;
}

export type BrowserSelectionUrlAdapterOptions = {
  readUrl: () => URL;
  replaceUrl: (url: URL) => void;
  parameter?: string;
};

export class BrowserSelectionUrlAdapter implements SelectionUrlPort {
  private readonly readUrl: () => URL;
  private readonly replaceUrl: (url: URL) => void;
  private readonly parameter: string;

  constructor(options: BrowserSelectionUrlAdapterOptions) {
    this.readUrl = options.readUrl;
    this.replaceUrl = options.replaceUrl;
    this.parameter = options.parameter ?? 'connector';
  }

  readSelection = (): string | null => this.readUrl().searchParams.get(this.parameter);

  replaceSelection = (selectionId: string): void => {
    const nextUrl = new URL(this.readUrl());
    nextUrl.searchParams.set(this.parameter, selectionId);
    this.replaceUrl(nextUrl);
  };
}

export class InMemorySelectionUrlAdapter implements SelectionUrlPort {
  selectionId: string | null;
  replacements: string[] = [];

  constructor(selectionId: string | null = null) {
    this.selectionId = selectionId;
  }

  readSelection = (): string | null => this.selectionId;

  replaceSelection = (selectionId: string): void => {
    this.selectionId = selectionId;
    this.replacements.push(selectionId);
  };
}
