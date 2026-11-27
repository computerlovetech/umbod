import { mount, tick, unmount } from 'svelte';
import { afterEach, expect, test } from 'vitest';
import ToolDescription from './ToolDescription.svelte';
import ToolParameterDetails from './ToolParameterDetails.svelte';

const components: ReturnType<typeof mount>[] = [];

afterEach(async (): Promise<void> => {
  await Promise.all(components.splice(0).map((component) => unmount(component)));
  document.body.replaceChildren();
});

function triggerNamed(name: string, root: ParentNode = document): HTMLButtonElement {
  const trigger = [...root.querySelectorAll('button')].find(
    (button) => (button.getAttribute('aria-label') ?? button.textContent?.trim()) === name
  );
  if (!trigger) throw new Error(`Missing trigger: ${name}`);
  return trigger;
}

function controlledPanel(trigger: HTMLButtonElement): HTMLElement {
  const id = trigger.getAttribute('aria-controls');
  const panel = id && document.getElementById(id);
  if (!panel) throw new Error('Missing controlled panel');
  return panel;
}

test('a multiline description swaps its preview for the full text and restores the preview when closed', async (): Promise<void> => {
  const description = 'First line.\nSecond line.';
  components.push(mount(ToolDescription, { target: document.body, props: { description } }));
  await tick();

  const trigger = document.querySelector('button');
  if (!trigger) throw new Error('Missing description trigger');
  const panel = controlledPanel(trigger);
  expect(trigger.textContent).toContain('Show full description');
  expect(trigger.querySelector('span[aria-hidden="true"]')?.textContent).toBe(description);
  expect(panel.hidden).toBe(true);

  trigger.click();
  await tick();
  expect(trigger.textContent?.trim()).toBe('Hide full description');
  expect(panel.hidden).toBe(false);
  expect(panel.querySelector('p')?.textContent).toBe(description);

  trigger.click();
  await tick();
  expect(trigger.textContent).toContain('Show full description');
  expect(trigger.querySelector('span[aria-hidden="true"]')?.textContent).toBe(description);
  expect(panel.hidden).toBe(true);
});

test('opening parameter details leaves the nested read-only schema closed until requested', async (): Promise<void> => {
  const inputSchema = { type: 'object', properties: { query: { type: 'string' } } };
  components.push(mount(ToolParameterDetails, { target: document.body, props: {
    parameters: [{ name: 'query', label: 'Query', type: 'string', description: 'Search text', required: true }],
    inputSchema
  } }));
  await tick();

  const trigger = triggerNamed('Toggle parameter schema details');
  const parameterPanel = controlledPanel(trigger);
  expect(trigger.textContent?.trim()).toBe('1 parameter · 1 required');
  expect(parameterPanel.hidden).toBe(true);

  trigger.click();
  await tick();
  expect(parameterPanel.hidden).toBe(false);
  expect(parameterPanel.textContent).toContain('Search text');
  const schemaTrigger = triggerNamed('Full input schema', parameterPanel);
  const schemaPanel = controlledPanel(schemaTrigger);
  expect(schemaPanel.hidden).toBe(true);

  schemaTrigger.click();
  await tick();
  expect(schemaPanel.hidden).toBe(false);
  const schema = schemaPanel.querySelector('textarea[aria-label="Full input schema (read-only)"]');
  if (!(schema instanceof HTMLTextAreaElement)) throw new Error('Missing input schema field');
  expect(schema.readOnly).toBe(true);
  expect(JSON.parse(schema.value)).toEqual(inputSchema);
});
