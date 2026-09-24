import {
  approvedHostnameSchema,
  importOpenApiCatalogUrlRequestSchema,
  OPEN_API_CATALOG_FILE_MAX_BYTES
} from '$lib/admin/openapi-connectors';

export type ImportMode = 'file' | 'url';

export class ImportCatalogState {
  mode = $state<ImportMode>('file');
  selectedFile = $state.raw<File>();
  fileError = $state('');
  hostInput = $state('');
  hostError = $state('');
  approvedHosts = $state<string[]>([]);
  url = $state('');
  urlError = $state('');
  fetchError = $state('');
  pending = $state(false);

  constructor(initial?: { mode: ImportMode; url?: string; approvedHosts?: string[] }) {
    if (initial !== undefined) {
      this.mode = initial.mode;
      this.url = initial.url ?? '';
      this.approvedHosts = initial.approvedHosts ?? [];
    }
  }

  setMode = (mode: ImportMode) => { this.mode = mode; this.fetchError = ''; };
  selectFiles = (files: ArrayLike<File>) => {
    this.fileError = '';
    this.selectedFile = undefined;
    if (files.length !== 1) { this.fileError = 'Choose exactly one JSON file.'; return; }
    const file = files[0];
    if (!file.name.toLowerCase().endsWith('.json') || file.type !== 'application/json') { this.fileError = 'Choose a .json file with the JSON content type.'; return; }
    if (file.size > OPEN_API_CATALOG_FILE_MAX_BYTES) { this.fileError = 'The JSON file must be 10 MiB or smaller.'; return; }
    this.selectedFile = file;
  };
  setHostInput = (value: string) => { this.hostInput = value; this.hostError = ''; };
  addHost = () => {
    const parsed = approvedHostnameSchema.safeParse(this.hostInput);
    if (!parsed.success) { this.hostError = 'Enter an exact hostname without a scheme, port, or path.'; return; }
    if (!this.approvedHosts.includes(parsed.data)) this.approvedHosts = [...this.approvedHosts, parsed.data];
    this.hostInput = '';
    this.hostError = '';
  };
  removeHost = (hostname: string) => { this.approvedHosts = this.approvedHosts.filter((value) => value !== hostname); };
  setUrl = (value: string) => {
    this.url = value;
    this.fetchError = '';
    const parsed = importOpenApiCatalogUrlRequestSchema.safeParse({ url: value });
    this.urlError = parsed.success ? '' : value.includes('@') ? 'URLs with embedded credentials are not allowed.' : 'Enter a valid HTTPS URL.';
  };
  beginFileSubmit = (): boolean => {
    if (this.fileError) return false;
    if (this.selectedFile === undefined) { this.fileError = 'Choose exactly one JSON file.'; return false; }
    const typedHost = this.hostInput.trim();
    if (typedHost && !approvedHostnameSchema.safeParse(typedHost).success) {
      this.hostError = 'Enter an exact hostname without a scheme, port, or path.';
      return false;
    }
    if (this.approvedHosts.length === 0 && !typedHost) { this.hostError = 'Add at least one exact hostname.'; return false; }
    this.pending = true;
    return true;
  };
  beginUrlSubmit = (): boolean => {
    this.setUrl(this.url);
    if (this.urlError) return false;
    const typedHost = this.hostInput.trim();
    if (typedHost && !approvedHostnameSchema.safeParse(typedHost).success) {
      this.hostError = 'Enter an exact hostname without a scheme, port, or path.';
      return false;
    }
    if (this.approvedHosts.length === 0 && !typedHost) { this.hostError = 'Add at least one exact hostname.'; return false; }
    this.pending = true;
    this.fetchError = '';
    return true;
  };
  finishSubmit = () => { this.pending = false; };
  fetchDocumentFromUrl = async (): Promise<{ ok: true; document: Record<string, unknown> } | { ok: false }> => {
    let response: Response;
    try {
      response = await fetch(this.url, { method: 'GET', credentials: 'omit', redirect: 'follow' });
    } catch {
      this.fetchError = 'The OpenAPI document could not be retrieved from that URL.';
      return { ok: false };
    }
    if (!response.ok) {
      this.fetchError = 'The OpenAPI document could not be retrieved from that URL.';
      return { ok: false };
    }
    const contentType = response.headers.get('content-type') ?? '';
    if (!contentType.includes('json') && !contentType.includes('text/plain') && contentType !== '') {
      this.fetchError = 'The URL did not return a JSON OpenAPI document.';
      return { ok: false };
    }
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      this.fetchError = 'The retrieved OpenAPI document is not valid JSON.';
      return { ok: false };
    }
    if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) {
      this.fetchError = 'The URL did not return a JSON object.';
      return { ok: false };
    }
    return { ok: true, document: payload as Record<string, unknown> };
  };
}
