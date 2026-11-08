import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';
import type { NodeSharingApi } from '../api';
import { sharingRecipientSearchResultSchema, type SharingRecipient, type SharingRecipientType } from '../domain/sharing';

export class RecipientSearchState {
  private text = $state('');
  private matches = $state.raw<readonly SharingRecipient[]>([]);
  private waiting = $state(false);
  private failure = $state('');
  private truncated = $state(false);
  private denied = $state(false);
  private nodeId = '';
  private recipientType: SharingRecipientType = 'group';
  private generation = 0;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private controller: AbortController | undefined;

  constructor(private readonly api: NodeSharingApi, private readonly authorityFailure: (error: unknown) => Promise<void>) {}

  get query(): string { return this.text; }
  get recipients(): readonly SharingRecipient[] { return this.matches; }
  get loading(): boolean { return this.waiting; }
  get error(): string { return this.failure; }
  get hasMore(): boolean { return this.truncated; }
  get unavailable(): boolean { return this.denied; }
  get emptyMessage(): string {
    if (this.waiting) return 'Searching…';
    if (this.failure) return 'Search unavailable';
    return this.text.trim() ? 'No recipients found' : 'Type a name to search';
  }

  target = (nodeId: string, recipientType: SharingRecipientType): void => {
    this.reset();
    this.nodeId = nodeId;
    this.recipientType = recipientType;
  };

  changeQuery = (value: string): void => {
    this.cancel();
    this.text = value;
    this.matches = [];
    this.failure = '';
    this.truncated = false;
    this.waiting = false;
    if (!value.trim() || !this.nodeId) return;
    if (value.trim().length > 200) {
      this.failure = 'Use at most 200 characters.';
      return;
    }
    this.waiting = true;
    this.timer = setTimeout(() => { void this.refresh(); }, 250);
  };

  refresh = async (): Promise<void> => {
    this.cancel();
    const query = this.text.trim();
    if (!query || query.length > 200 || !this.nodeId) return;
    const generation = this.generation;
    this.controller = new AbortController();
    this.waiting = true;
    this.failure = '';
    try {
      const result = sharingRecipientSearchResultSchema.parse(await this.api.searchRecipients(this.nodeId, query, this.recipientType, this.controller.signal));
      if (generation !== this.generation) return;
      this.matches = Object.freeze(result.recipients.filter((recipient) => recipient.type === this.recipientType).map((recipient) => Object.freeze(recipient)));
      this.truncated = result.has_more;
    } catch (error) {
      if (generation !== this.generation) return;
      if (error instanceof AuthenticationRequiredError || error instanceof HttpError && [401, 403, 404].includes(error.status)) {
        this.denied = true;
        this.failure = 'You are not authorized to search these recipients.';
        await this.authorityFailure(error);
      } else this.failure = "Couldn't search recipients. Try again.";
    } finally {
      if (generation === this.generation) this.waiting = false;
    }
  };

  reset = (): void => {
    this.cancel();
    this.nodeId = '';
    this.text = '';
    this.matches = [];
    this.waiting = false;
    this.failure = '';
    this.truncated = false;
    this.denied = false;
  };

  private cancel(): void {
    ++this.generation;
    clearTimeout(this.timer);
    this.timer = undefined;
    this.controller?.abort();
    this.controller = undefined;
  }
}
