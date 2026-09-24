import { z } from "zod";

const clipboardTextSchema = z.string();
const clipboardWriteResultSchema = z.void();

export interface ClipboardWriter {
  writeText(text: string): Promise<void>;
}

export class BrowserNavigatorClipboardWriter implements ClipboardWriter {
  async writeText(text: string): Promise<void> {
    const validatedText = clipboardTextSchema.parse(text);
    try {
      const result = await navigator.clipboard.writeText(validatedText);
      clipboardWriteResultSchema.parse(result);
    } catch {
      const field = document.createElement("textarea");
      field.value = validatedText;
      field.style.position = "fixed";
      field.style.opacity = "0";
      document.body.appendChild(field);
      field.select();
      const copied = document.execCommand("copy");
      field.remove();
      if (!copied) {
        throw new Error("Clipboard write failed");
      }
    }
  }
}

export class BrowserClipboardWriter extends BrowserNavigatorClipboardWriter {}

export class InMemoryClipboardWriter implements ClipboardWriter {
  text = "";

  constructor(private readonly failure: Error | null = null) {}

  async writeText(text: string): Promise<void> {
    if (this.failure) throw this.failure;
    this.text = clipboardTextSchema.parse(text);
    clipboardWriteResultSchema.parse(undefined);
  }
}
