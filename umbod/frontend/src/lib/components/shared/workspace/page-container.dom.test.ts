import { afterEach, expect, test } from 'vitest';
import { mount, tick, unmount, type ComponentProps } from 'svelte';
import { SvelteMap } from 'svelte/reactivity';
import Harness from './page-container.test-support.svelte';

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
});

async function renderContainer(showActions: boolean): Promise<SvelteMap<string, ComponentProps<typeof Harness>>> {
  const values = new SvelteMap([['current', { title: 'Items', detail: 'Initial details', showActions }]]);
  component = mount(Harness, {
    target: document.body,
    props: {
      get title(): string { return values.get('current')!.title; },
      get detail(): string { return values.get('current')!.detail; },
      get showActions(): boolean { return values.get('current')!.showActions; }
    }
  });
  await tick();
  return values;
}

function element<T extends Element = HTMLElement>(selector: string): T {
  const found = document.querySelector<T>(selector);
  if (!found) throw new Error(`Expected mounted element: ${selector}`);
  return found;
}

test('places caller identity and actions in the heading and supplied content below it', async (): Promise<void> => {
  await renderContainer(true);
  const root = element('.page-container');
  const heading = element('header.page-container-heading');
  const identity = element('.page-container-identity');
  const actions = element('.page-container-actions');
  const content = element('.page-container-content');

  expect(Array.from(root.children)).toEqual([heading, content]);
  expect(Array.from(heading.children)).toEqual([identity, actions]);
  expect(identity.querySelector('h1')?.textContent).toBe('Items');
  expect(actions.querySelector('button')?.textContent).toBe('Create item');
  expect(content.querySelector('section')?.textContent).toBe('Initial details');
  expect(actions.hasAttribute('role')).toBe(false);
  expect(actions.hasAttribute('aria-label')).toBe(false);
});

test('omits the actions wrapper when the caller supplies no actions', async (): Promise<void> => {
  await renderContainer(false);
  expect(document.querySelector('.page-container-actions')).toBeNull();
  expect(element('.page-container-heading').children).toHaveLength(1);
  expect(element('h1').textContent).toBe('Items');
  expect(element('.page-container-content section').textContent).toBe('Initial details');
});

test('keeps the heading outside caller-supplied sidebar and detail content', async (): Promise<void> => {
  await renderContainer(true);
  const heading = element('.page-container-heading');
  const content = element('.page-container-content');
  const sidebar = element('aside');
  const detail = element('section');

  expect(content.contains(sidebar)).toBe(true);
  expect(content.contains(detail)).toBe(true);
  expect(sidebar.contains(heading)).toBe(false);
  expect(detail.contains(heading)).toBe(false);
  expect(heading.contains(sidebar)).toBe(false);
  expect(heading.contains(detail)).toBe(false);
});

test('updates caller props and content without replacing identity or content DOM', async (): Promise<void> => {
  const values = await renderContainer(false);
  const root = element('.page-container');
  const heading = element('.page-container-heading');
  const identity = element('.page-container-identity');
  const title = element('h1');
  const content = element('.page-container-content');
  const sidebar = element('aside');
  const detail = element('section');
  const paragraph = element('section p');
  const draft = element<HTMLInputElement>('input');
  draft.value = 'Unsaved draft';
  draft.focus();

  values.set('current', { title: 'Updated items', detail: 'Updated details', showActions: true });
  await tick();

  expect(element('.page-container')).toBe(root);
  expect(element('.page-container-heading')).toBe(heading);
  expect(element('.page-container-identity')).toBe(identity);
  expect(element('h1')).toBe(title);
  expect(title.textContent).toBe('Updated items');
  expect(element('.page-container-content')).toBe(content);
  expect(element('aside')).toBe(sidebar);
  expect(element('section')).toBe(detail);
  expect(element('section p')).toBe(paragraph);
  expect(paragraph.textContent).toBe('Updated details');
  expect(element('input')).toBe(draft);
  expect(draft.value).toBe('Unsaved draft');
  expect(document.activeElement).toBe(draft);
  expect(element('.page-container-actions button').textContent).toBe('Create item');
});
