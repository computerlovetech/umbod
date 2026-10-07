import type { InstanceConfiguration, InstanceConfigurationEntry } from '$lib/admin/instance-configuration';

export type SettingSection = 'access' | 'tools' | 'addresses' | 'advanced';
export type PresentedSetting = {
  entry: InstanceConfigurationEntry;
  label: string;
  description: string;
  values: string[];
  address: boolean;
};
export type SettingsPresentation = {
  essentials: { variable: string; label: string; value: string }[];
  access: PresentedSetting[];
  tools: PresentedSetting[];
  addresses: PresentedSetting[];
  advanced: { id: string; label: string; entries: PresentedSetting[] }[];
};

type SettingDefinition = { section: SettingSection; label: string; description: string };
const definitions: Record<string, SettingDefinition> = {};

function define(section: SettingSection, suffix: string, label: string, description: string): void {
  definitions[`UMBOD_${suffix}`] = { section, label, description };
}

define('access', 'AUTH', 'Sign-in method', 'How people sign in to this instance.');
define('access', 'OIDC_ISSUER_URL', 'Sign-in provider', 'The expected issuer of sign-in tokens.');
define('access', 'ADMIN_GROUP', 'Administrator access', 'The group whose members can access administration.');
define('access', 'FEATURE_MCP_ADMINISTRATOR_ENABLED', 'MCP administrator tools', 'Whether administration tools are exposed through MCP.');
define('advanced', 'MCP_PERMISSION_CLAIM', 'Permission group field', 'The token field used to read tool permission groups.');
define('advanced', 'OIDC_CONFIG_URL', 'Sign-in discovery address', 'Where sign-in provider configuration is retrieved.');
define('advanced', 'OIDC_CLIENT_ID', 'Sign-in application ID', 'The public identifier for this instance at the sign-in provider.');
define('advanced', 'OIDC_AUDIENCE', 'Token audience', 'The audience expected in sign-in tokens.');
define('advanced', 'OIDC_TENANT_ID', 'Sign-in tenant', 'The identity-provider tenant for this instance.');
define('advanced', 'OIDC_REQUIRED_SCOPES', 'Required sign-in scopes', 'The scopes required when signing in.');
define('tools', 'MCP_TOOL_EXPOSURE', 'Tool presentation', 'How connector tools are offered to MCP clients.');
define('tools', 'MCP_CODE_EXECUTION_TIMEOUT_SECONDS', 'Code execution limit', 'How long connector code may run.');
define('tools', 'MCP_MAXIMUM_UPLOADED_FILE_BYTES', 'Upload size limit', 'The largest file accepted as connector input.');
define('tools', 'MCP_DOWNSTREAM_DISCOVERY_ENABLED', 'Connected server discovery', 'Whether tools are discovered from connected MCP servers.');
define('tools', 'OPENAPI_JSON_IMPORT_MAX_BYTES', 'OpenAPI import size limit', 'The largest OpenAPI JSON document accepted for import.');
define('tools', 'OPENAPI_URL_RETRIEVAL_TIMEOUT_SECONDS', 'OpenAPI retrieval limit', 'How long fetching an OpenAPI document may take.');
define('tools', 'OPENAPI_EXECUTION_READ_TIMEOUT_SECONDS', 'OpenAPI response wait limit', 'How long a connector waits to read a response.');
define('addresses', 'PUBLIC_SITE_ORIGIN', 'Web address', 'The configured public address for the web interface.');
define('addresses', 'PUBLIC_API_ORIGIN', 'API address', 'The configured public address for the REST API.');
define('addresses', 'PUBLIC_MCP_ORIGIN', 'MCP address', 'The configured public address for MCP clients.');
define('addresses', 'CORS_ORIGINS', 'Allowed browser origins', 'Web origins permitted to make cross-origin requests.');
define('advanced', 'APP_NAME', 'Instance name', 'The name used to identify this instance.');
define('advanced', 'PROFILE', 'Environment', 'The deployment profile configured for this instance.');

define('advanced', 'LOG_LEVEL', 'Logging detail', 'The minimum severity recorded in application logs.');
define('advanced', 'CONNECTOR_STORE', 'Connector storage', 'Where connector data is persisted.');
define('advanced', 'OTLP_ENABLED', 'Telemetry ingestion', 'Whether this instance accepts telemetry batches.');
define('advanced', 'OTLP_ALLOW_UNAUTHENTICATED', 'Unauthenticated local telemetry', 'Whether local telemetry ingestion can bypass authentication.');
define('advanced', 'OTLP_MAX_REQUEST_BYTES', 'Telemetry batch limit', 'The maximum telemetry request size before and after decompression.');
define('advanced', 'MCP_DOWNSTREAM_DISCOVERY_TIMEOUT_SECONDS', 'Server discovery time limit', 'How long connected server discovery may take.');
define('advanced', 'MCP_DOWNSTREAM_REFRESH_INTERVAL_SECONDS', 'Server refresh interval', 'How often connected server tools are refreshed.');
define('advanced', 'MCP_DOWNSTREAM_DISCOVERY_CONCURRENCY', 'Parallel server discovery', 'The maximum number of simultaneous server discovery operations.');
define('advanced', 'MCP_DOWNSTREAM_DISCOVERY_JITTER_RATIO', 'Discovery schedule variation', 'The variation applied to connected server discovery scheduling.');
define('advanced', 'MCP_DOWNSTREAM_DISCOVERY_MAXIMUM_BACKOFF_SECONDS', 'Discovery retry delay limit', 'The longest delay between discovery retries.');
define('advanced', 'MCP_AUTH_DEBUG_ENABLED', 'MCP authentication diagnostics', 'Whether additional MCP authentication diagnostics are enabled.');
define('advanced', 'MCP_STATELESS_HTTP', 'Session-free MCP transport', 'Whether MCP HTTP requests operate without session state.');
define('advanced', 'OPENAPI_EXECUTION_CONNECT_TIMEOUT_SECONDS', 'OpenAPI connection limit', 'How long establishing a connector connection may take.');
define('advanced', 'OPENAPI_EXECUTION_WRITE_TIMEOUT_SECONDS', 'OpenAPI request send limit', 'How long sending a connector request may take.');
define('advanced', 'OPENAPI_EXECUTION_POOL_TIMEOUT_SECONDS', 'OpenAPI connection wait limit', 'How long a connector waits for an available connection.');
define('advanced', 'ADMIN_JWT_HEADER', 'Administrator token header', 'The request header carrying the administrator sign-in token.');
define('advanced', 'ADMIN_JWKS_URL', 'Token verification keys address', 'Where administrator token verification keys are retrieved.');
define('advanced', 'ADMIN_MEMBERSHIP_CLAIM', 'Administrator membership field', 'The token field containing administrator group memberships.');
define('advanced', 'ADMIN_AUTHENTICATION_DEBUG_ENABLED', 'Administrator sign-in diagnostics', 'Whether additional administrator authentication diagnostics are enabled.');

const durationVariables = new Set([
  'MCP_CODE_EXECUTION_TIMEOUT_SECONDS', 'MCP_DOWNSTREAM_DISCOVERY_TIMEOUT_SECONDS',
  'MCP_DOWNSTREAM_REFRESH_INTERVAL_SECONDS', 'MCP_DOWNSTREAM_DISCOVERY_MAXIMUM_BACKOFF_SECONDS',
  'OPENAPI_URL_RETRIEVAL_TIMEOUT_SECONDS', 'OPENAPI_EXECUTION_CONNECT_TIMEOUT_SECONDS',
  'OPENAPI_EXECUTION_READ_TIMEOUT_SECONDS', 'OPENAPI_EXECUTION_WRITE_TIMEOUT_SECONDS',
  'OPENAPI_EXECUTION_POOL_TIMEOUT_SECONDS'
].map((suffix: string): string => `UMBOD_${suffix}`));
const byteVariables = new Set(['OTLP_MAX_REQUEST_BYTES', 'MCP_MAXIMUM_UPLOADED_FILE_BYTES', 'OPENAPI_JSON_IMPORT_MAX_BYTES'].map((suffix: string): string => `UMBOD_${suffix}`));

export function displayValues(entry: InstanceConfigurationEntry): string[] {
  if (entry.type === 'string_list') return entry.value.length ? entry.value : ['None configured'];
  if (entry.type === 'boolean') return [entry.value ? 'Enabled' : 'Disabled'];
  if (entry.type === 'string') {
    if (entry.value === '') return ['Not set'];
    if (entry.variable === 'UMBOD_PROFILE' && entry.value === 'local') return ['Local development'];
    if (entry.variable === 'UMBOD_AUTH' && entry.value === 'dev') return ['Development authentication'];
    if (entry.variable === 'UMBOD_ADMIN_GROUP') return [`Members of ${entry.value}`];
    if (entry.variable === 'UMBOD_MCP_TOOL_EXPOSURE' && entry.value === 'flat') return ['Direct tools only'];
    return [entry.value];
  }
  if (durationVariables.has(entry.variable)) return [`${entry.value} ${entry.value === 1 ? 'second' : 'seconds'}`];
  if (byteVariables.has(entry.variable)) {
    const units = [{ divisor: 1073741824, label: 'GiB' }, { divisor: 1048576, label: 'MiB' }, { divisor: 1024, label: 'KiB' }];
    const unit = units.find((candidate): boolean => entry.value >= candidate.divisor);
    return [unit ? `${Number((entry.value / unit.divisor).toFixed(2))} ${unit.label}` : `${entry.value} ${entry.value === 1 ? 'byte' : 'bytes'}`];
  }
  if (entry.variable === 'UMBOD_MCP_DOWNSTREAM_DISCOVERY_JITTER_RATIO') return [`${Number((entry.value * 100).toFixed(2))}%`];
  return [String(entry.value)];
}

export function presentConfiguration(configuration: InstanceConfiguration): SettingsPresentation {
  const result: SettingsPresentation = { essentials: [], access: [], tools: [], addresses: [], advanced: [] };
  const allEntries = configuration.groups.flatMap((group) => group.entries);
  const summaryFields = [
    ['UMBOD_APP_NAME', 'Instance name'], ['UMBOD_PROFILE', 'Environment'],
    ['UMBOD_AUTH', 'Sign-in method'], ['UMBOD_ADMIN_GROUP', 'Administrator access'],
    ['UMBOD_FEATURE_MCP_ADMINISTRATOR_ENABLED', 'MCP administrator tools']
  ];
  result.essentials = summaryFields.map(([variable, label]) => {
    const entry = allEntries.find((candidate): boolean => candidate.variable === variable);
    return { variable, label, value: entry ? displayValues(entry).join(', ') : 'Not available' };
  });
  for (const group of configuration.groups) {
    const advancedEntries: PresentedSetting[] = [];
    for (const entry of group.entries) {
      const definition = definitions[entry.variable];
      const presented: PresentedSetting = {
        entry, label: definition?.label ?? entry.label,
        description: definition?.description ?? entry.description,
        values: displayValues(entry),
        address: definition?.section === 'addresses' && entry.type === 'string' && entry.value !== ''
      };
      const section = definition?.section ?? 'advanced';
      if (section === 'advanced') advancedEntries.push(presented);
      else result[section].push(presented);
    }
    if (advancedEntries.length) result.advanced.push({ id: group.id, label: group.label, entries: advancedEntries });
  }
  const orderedVariables = Object.keys(definitions);
  for (const section of ['access', 'tools', 'addresses'] as const) {
    result[section].sort((first, second): number => orderedVariables.indexOf(first.entry.variable) - orderedVariables.indexOf(second.entry.variable));
  }
  return result;
}
