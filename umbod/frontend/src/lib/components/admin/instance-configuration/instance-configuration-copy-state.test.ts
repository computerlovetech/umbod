import { describe, expect, it } from "vitest";
import { InMemoryClipboardWriter } from "$lib/admin/clipboard";
import type { InstanceConfiguration } from "$lib/admin/instance-configuration";
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
