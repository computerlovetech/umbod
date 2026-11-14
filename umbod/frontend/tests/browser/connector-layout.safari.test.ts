import { spawn, type ChildProcess } from 'node:child_process';
import { afterAll, beforeAll, expect, test, vi } from 'vitest';
import { z } from 'zod';

const driverUrl = 'http://localhost:4445';
const applicationUrl = process.env.UMBOD_UI_TEST_URL ?? 'http://localhost:3010';
const elementKey = 'element-6066-11e4-a52e-4f735466cecf';
const elementSchema = z.object({ [elementKey]: z.string() });
const geometrySchema = z.object({
  inputTop: z.number(),
  inputBottom: z.number(),
  fieldBottom: z.number(),
  nextLabelTop: z.number(),
  outlineWidth: z.number(),
  outlineOffset: z.number(),
  inputFocused: z.boolean(),
  selectedText: z.string()
});
let driver: ChildProcess | undefined;
let sessionId: string | undefined;

async function request(path: string, body?: unknown, method: string = body === undefined ? 'GET' : 'POST'): Promise<unknown> {
  const response = await fetch(`${driverUrl}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    signal: AbortSignal.timeout(60000),
    ...(body === undefined ? {} : { body: JSON.stringify(body) })
  });
  const payload = z.object({ value: z.unknown() }).parse(await response.json());
  if (!response.ok) throw new Error(`Safari WebDriver ${response.status}: ${JSON.stringify(payload.value)}`);
  return payload.value;
}

function sessionPath(path: string): string {
  if (!sessionId) throw new Error('Safari session has not started');
  return `/session/${sessionId}${path}`;
}

async function click(using: string, value: string): Promise<void> {
  const element = await vi.waitFor(async (): Promise<z.infer<typeof elementSchema>> => elementSchema.parse(await request(sessionPath('/element'), { using, value })), { timeout: 10000 });
  await request(sessionPath(`/element/${element[elementKey]}/click`), {});
}

async function geometry(): Promise<z.infer<typeof geometrySchema>> {
  return geometrySchema.parse(await request(sessionPath('/execute/sync'), {
    script: `const input = document.querySelector('dialog[open] input[name="displayName"]');
      const field = input.closest('.form-field');
      const label = field.nextElementSibling.querySelector('label');
      const style = getComputedStyle(input);
      return {
        inputTop: input.getBoundingClientRect().top,
        inputBottom: input.getBoundingClientRect().bottom,
        fieldBottom: field.getBoundingClientRect().bottom,
        nextLabelTop: label.getBoundingClientRect().top,
        outlineWidth: parseFloat(style.outlineWidth),
        outlineOffset: parseFloat(style.outlineOffset),
        inputFocused: document.activeElement === input,
        selectedText: window.getSelection().toString()
      };`,
    args: []
  }));
}

async function expectClearFocusRing(): Promise<void> {
  const bounds = await geometry();
  expect(bounds.inputFocused).toBe(true);
  expect(bounds.selectedText).toBe('');
  expect(bounds.fieldBottom).toBeGreaterThanOrEqual(bounds.inputBottom);
  expect(bounds.nextLabelTop).toBeGreaterThan(bounds.inputBottom + bounds.outlineWidth + bounds.outlineOffset);
}

beforeAll(async (): Promise<void> => {
  driver = spawn('/usr/bin/safaridriver', ['--port', '4445'], { stdio: 'inherit' });
  await vi.waitFor(async (): Promise<void> => {
    await request('/status');
  }, { timeout: 5000 });
  const session = z.object({ sessionId: z.string() }).parse(await request('/session', {
    capabilities: { alwaysMatch: { browserName: 'safari' } }
  }));
  sessionId = session.sessionId;
});

afterAll(async (): Promise<void> => {
  try {
    if (sessionId) await request(sessionPath(''), undefined, 'DELETE');
  } finally {
    driver?.kill();
  }
});

for (const height of [633, 900]) {
  test(`MCP initial focus and refocus do not overlap the next label at ${height}px`, async (): Promise<void> => {
    await request(sessionPath('/window/rect'), { width: 1280, height });
    await request(sessionPath('/url'), { url: `${applicationUrl}/admin/downstream-mcp-connectors` });
    await click('xpath', '//button[normalize-space()="Add MCP connector"]');
    await click('xpath', '//button[normalize-space()="Shared"]');
    await vi.waitFor(async (): Promise<void> => {
      const bounds = await geometry();
      expect(bounds.inputFocused).toBe(false);
      expect(bounds.selectedText).toBe('');
    }, { timeout: 5000 });
    const before = await geometry();
    await click('css selector', 'dialog[open] input[name="displayName"]');
    const focused = await geometry();
    expect(Math.abs((focused.nextLabelTop - focused.inputTop) - (before.nextLabelTop - before.inputTop))).toBeLessThan(1);
    await expectClearFocusRing();
    await click('css selector', 'dialog[open] input[name="toolNamePrefix"]');
    await click('css selector', 'dialog[open] input[name="displayName"]');
    await expectClearFocusRing();
  });
}
