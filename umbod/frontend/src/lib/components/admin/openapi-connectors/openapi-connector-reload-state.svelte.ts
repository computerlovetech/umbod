export class OpenApiConnectorReloadState {
  retrying = $state(false);
  private readonly reload: (() => Promise<void>) | null;

  constructor(reload?: () => Promise<void>) {
    this.reload = reload ?? null;
  }

  retry = async (): Promise<void> => {
    if (this.reload === null) return;
    this.retrying = true;
    try {
      await this.reload();
    } finally {
      this.retrying = false;
    }
  };
}
