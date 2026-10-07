import { describe, expect, it } from "vitest";
import { InMemoryClipboardWriter } from "$lib/admin/clipboard";
import type { InstanceConfiguration, InstanceConfigurationEntry } from "$lib/admin/instance-configuration";
import { InstanceConfigurationCopyState } from "./instance-configuration-copy-state.svelte";
import { ToastState } from "$lib/components/feedback/toast-state.svelte";

const configuration: InstanceConfiguration = {
  groups: [
    {
      id: "endpoints",
      label: "Endpoints",
      entries: [
        {
          variable: "UMBOD_PUBLIC_MCP_ORIGIN",
          label: "Public MCP origin",
          description: "Public MCP endpoint.",
          type: "string",
          value: "https://mcp.example.com",
        },
        {
          variable: "UMBOD_CORS_ORIGINS",
          label: "CORS origins",
          description: "Allowed origins.",
          type: "string_list",
          value: ["https://one.example.com", "https://two.example.com"],
        },
      ],
    },
  ],
};

describe("instance configuration copying", () => {
  it.each([
    [{ variable: 'zero', label: 'Zero', description: '', type: 'integer', value: 0 }, '0'],
    [{ variable: 'false', label: 'False', description: '', type: 'boolean', value: false }, 'false'],
    [{ variable: 'empty', label: 'Empty', description: '', type: 'string', value: '' }, ''],
    [{ variable: 'list', label: 'List', description: '', type: 'string_list', value: ['one', 'two'] }, 'one, two'],
    [{ variable: 'empty-list', label: 'Empty list', description: '', type: 'string_list', value: [] }, '']
  ] satisfies [InstanceConfigurationEntry, string][])('copies exact raw values for %j', async (entry, expected) => {
    const clipboard = new InMemoryClipboardWriter();
    const state = new InstanceConfigurationCopyState(clipboard, new ToastState());
    await state.copyEntry(entry);
    expect(clipboard.text).toBe(expected);
  });

  it('only reports copied feedback for the successful value under its current variable', async () => {
    const state = new InstanceConfigurationCopyState(new InMemoryClipboardWriter(), new ToastState());
    const entry = configuration.groups[0].entries[0];
    await state.copyEntry(entry);
    expect(state.isCopied(entry)).toBe(true);
    expect(state.isCopied({ ...entry, value: 'https://updated.example.com', type: 'string' })).toBe(false);
    expect(state.isCopied({ ...entry, variable: 'UMBOD_PUBLIC_SITE_ORIGIN' })).toBe(false);
  });

  it('reports clipboard failure without claiming a successful copy', async () => {
    const toast = new ToastState();
    const state = new InstanceConfigurationCopyState({ writeText: async (): Promise<void> => { throw new Error('Denied'); } }, toast);
    await state.copyEntry(configuration.groups[0].entries[0]);
    expect(state.copiedTarget).toBeNull();
    expect(state.isCopied(configuration.groups[0].entries[0])).toBe(false);
    expect(state.copyFailed).toBe(true);
    expect(toast.toasts[0]?.message).toBe('Could not copy to the clipboard.');
  });
  it("copies an individual effective value", async () => {
    const clipboard = new InMemoryClipboardWriter();
    const toast = new ToastState();
    const state = new InstanceConfigurationCopyState(clipboard, toast);

    await state.copyEntry(configuration.groups[0].entries[0]);

    expect(clipboard.text).toBe("https://mcp.example.com");
    expect(state.copiedTarget).toBe("UMBOD_PUBLIC_MCP_ORIGIN");
    expect(toast.toasts[0]?.message).toBe("Value copied.");
  });
});
