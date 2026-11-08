export class McpSetupState {
  constructor(private readonly endpoint: () => string) {}

  get codexCommand(): string {
    return `codex mcp add umbod --url ${this.shellEndpoint}`;
  }

  get claudeCommand(): string {
    return `claude mcp add --transport http --scope user umbod ${this.shellEndpoint}`;
  }

  private get shellEndpoint(): string {
    return `'${this.endpoint().replaceAll("'", "'\\''")}'`;
  }
}
