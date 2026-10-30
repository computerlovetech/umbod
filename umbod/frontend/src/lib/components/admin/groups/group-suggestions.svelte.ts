import type { IdentityGroupDirectory } from '$lib/identity-directory/port';

export class GroupSuggestions {
  private values = $state.raw<string[]>([]);
  private generation = 0;
  private active = false;
  constructor(private readonly directory: IdentityGroupDirectory) {}
  get options(): readonly string[] { return this.values; }
  open = (): void => { this.active = true; this.search(''); };
  close = (): void => { this.active = false; ++this.generation; this.values = []; };
  search = (query: string): void => {
    if (!this.active) return;
    const generation = ++this.generation;
    void this.load(query, generation);
  };
  private async load(query: string, generation: number): Promise<void> {
    try {
      const result = await this.directory.list({ query, limit: 50 });
      if (this.active && generation === this.generation) this.values = result.groups.map((group) => group.value);
    } catch {
      if (generation === this.generation) this.values = [];
    }
  }
}
