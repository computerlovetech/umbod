import { OPEN_API_CATALOG_FILE_MAX_BYTES } from '$lib/admin/openapi-connectors';
import { describe, expect, test, vi } from 'vitest';
import { ImportCatalogState } from './import-catalog-state.svelte';

describe('ImportCatalogState', () => {
  test('accepts a JSON file at exactly the 10 MiB limit', () => {
    const state = new ImportCatalogState();
    const file = new File([new Uint8Array(OPEN_API_CATALOG_FILE_MAX_BYTES)], 'api.json', { type: 'application/json' });

    state.selectFiles([file]);

    expect(state.fileError).toBe('');
    expect(state.selectedFile).toBe(file);
  });

  test('rejects a JSON file one byte over the limit before submit and clears the error for a valid replacement', () => {
    const state = new ImportCatalogState();
    state.setHostInput('api.example.com');
    state.addHost();

    state.selectFiles([new File([new Uint8Array(OPEN_API_CATALOG_FILE_MAX_BYTES + 1)], 'api.json', { type: 'application/json' })]);

    expect(state.fileError).toBe('The JSON file must be 10 MiB or smaller.');
    expect(state.beginFileSubmit()).toBe(false);
    expect(state.pending).toBe(false);

    const replacement = new File(['{}'], 'replacement.json', { type: 'application/json' });
    state.selectFiles([replacement]);

    expect(state.fileError).toBe('');
    expect(state.selectedFile).toBe(replacement);
    expect(state.beginFileSubmit()).toBe(true);
  });

  test('rejects files that are not JSON', () => {
    const state = new ImportCatalogState();
    state.selectFiles([new File(['{}'], 'api.yaml', { type: 'application/yaml' })]);
    expect(state.fileError).toMatch(/JSON/);
  });

  test('normalizes exact approved hostnames and rejects unsafe values', () => {
    const state = new ImportCatalogState();
    state.setHostInput(' API.Example.com ');
    state.addHost();
    expect(state.approvedHosts).toEqual(['api.example.com']);
    state.setHostInput('https://api.example.com/path');
    state.addHost();
    expect(state.hostError).toMatch(/hostname/);
  });

  test('requires HTTPS URLs without embedded credentials', () => {
    const state = new ImportCatalogState();
    state.setUrl('http://api.example.com/openapi.json');
    expect(state.urlError).toMatch(/HTTPS/);
    state.setUrl('https://user:secret@api.example.com/openapi.json');
    expect(state.urlError).toMatch(/credentials/);
    state.setUrl('https://api.example.com/openapi.json');
    expect(state.urlError).toBe('');
  });

  test('requires approved hosts before URL submit and fetches a JSON object in the browser', async () => {
    const state = new ImportCatalogState();
    state.setMode('url');
    state.setUrl('https://api.example.com/openapi.json');
    expect(state.beginUrlSubmit()).toBe(false);
    expect(state.hostError).toMatch(/hostname/);
    state.setHostInput('api.example.com');
    state.addHost();
    expect(state.beginUrlSubmit()).toBe(true);
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ openapi: '3.1.0' }), {
      status: 200,
      headers: { 'content-type': 'application/json' }
    }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(state.fetchDocumentFromUrl()).resolves.toEqual({ ok: true, document: { openapi: '3.1.0' } });
    expect(fetchMock).toHaveBeenCalledWith('https://api.example.com/openapi.json', expect.objectContaining({ method: 'GET', credentials: 'omit' }));
    vi.unstubAllGlobals();
  });
});
