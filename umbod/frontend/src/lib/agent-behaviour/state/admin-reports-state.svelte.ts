import type { ReportsPort } from '../api';
import { ReportsState, type ReportLabels } from './reports-state.svelte';

export class AdminReportsState extends ReportsState {
  private deleteConfirmationValue = $state(false);

  constructor(private readonly adminApi: ReportsPort, revoke: () => void, labels?: () => ReportLabels) {
    super(adminApi, revoke, labels);
  }

  get deleteConfirmation(): boolean { return this.deleteConfirmationValue; }

  override async open(id: string): Promise<void> {
    if (!this.deleteConfirmation) await super.open(id);
  }

  protected override closeDetail(): void {
    super.closeDetail();
    this.deleteConfirmationValue = false;
  }

  confirmDelete = (): void => { if (this.detail && !this.detailBusy) this.deleteConfirmationValue = true; };
  cancelDelete = (): void => { this.deleteConfirmationValue = false; };

  remove = async (): Promise<void> => {
    const detail = this.detail;
    if (this.disposed || !detail || !this.deleteConfirmation || this.detailBusy) return;
    await this.runDetailRequest(async (request): Promise<void> => {
      await this.adminApi.remove(detail.report_id, request.signal);
      if (!this.isCurrentDetailRequest(request)) return;
      this.close();
      await this.load();
    }, 'This entry could not be deleted. Try again.');
  };
}
