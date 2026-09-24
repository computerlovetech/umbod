import { describe, expect, it } from 'vitest';
import { InMemoryClipboardWriter, type ClipboardWriter } from '$lib/admin/clipboard';
import { CopyableValueState } from './copyable-value-state.svelte';
import { ToastState } from '$lib/components/feedback/toast-state.svelte';

async function copyThroughPort(clipboard: ClipboardWriter, value: string): Promise<void> {
  await clipboard.writeText(value);
}

describe('copyable value clipboard contract', () => {
  it('writes the complete value through the clipboard port', async () => {
    const clipboard = new InMemoryClipboardWriter();

    await copyThroughPort(clipboard, 'https://agent.test/mcp/proxies/payments');

    expect(clipboard.text).toBe('https://agent.test/mcp/proxies/payments');
  });

  it('reports successful copies through its public state', async () => {
    const clipboard = new InMemoryClipboardWriter();
    const toast = new ToastState();
    const state = new CopyableValueState('connector-id', clipboard, toast);

    await state.copy();

    expect(state.feedback).toBe('copied');
    expect(clipboard.text).toBe('connector-id');
    expect(toast.toasts[0]?.message).toBe('URI copied to clipboard');
  });

  it('reports clipboard failures through its public state', async () => {
    const toast = new ToastState();
    const state = new CopyableValueState('connector-id', new InMemoryClipboardWriter(new Error('unavailable')), toast);

    await state.copy();

    expect(state.feedback).toBe('failed');
    expect(toast.toasts[0]?.message).toBe('Could not copy URI');
  });
});
