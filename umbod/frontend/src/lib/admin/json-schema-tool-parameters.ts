import type { ConnectorToolParameter } from './connectors';

type JsonSchema = Record<string, unknown>;

function isRecord(value: unknown): value is JsonSchema {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function formatLabel(name: string): string {
  const label = name.replaceAll('_', ' ').replace(/([a-z0-9])([A-Z])/g, '$1 $2');
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function resolveReference(schema: JsonSchema, rootSchema: JsonSchema): JsonSchema {
  if (typeof schema.$ref !== 'string' || !schema.$ref.startsWith('#/')) return schema;
  const resolved = schema.$ref
    .slice(2)
    .split('/')
    .reduce<unknown>((value, segment) => isRecord(value) ? value[segment.replaceAll('~1', '/').replaceAll('~0', '~')] : undefined, rootSchema);
  return isRecord(resolved) ? resolved : schema;
}

function schemaType(schema: JsonSchema, rootSchema: JsonSchema): string {
  const resolvedSchema = resolveReference(schema, rootSchema);
  if (resolvedSchema !== schema) return schemaType(resolvedSchema, rootSchema);
  if (typeof schema.type === 'string') return schema.type;
  if (Array.isArray(schema.type)) {
    const types = schema.type.filter((value): value is string => typeof value === 'string');
    return types.length > 0 ? types.join(' | ') : 'unknown';
  }
  for (const composition of ['oneOf', 'anyOf', 'allOf'] as const) {
    const members = schema[composition];
    if (Array.isArray(members)) {
      const types = [...new Set(members.filter(isRecord).map((member) => schemaType(member, rootSchema)))];
      return types.length > 0 ? types.join(composition === 'allOf' ? ' & ' : ' | ') : 'unknown';
    }
  }
  return 'unknown';
}

function parameterObjectSchema(schema: JsonSchema): JsonSchema {
  if (!isRecord(schema.properties)) return schema;
  const properties = Object.values(schema.properties);
  if (properties.length !== 1 || !isRecord(properties[0])) return schema;
  const propertySchema = resolveReference(properties[0], schema);
  return isRecord(propertySchema.properties) ? propertySchema : schema;
}

export function mapJsonSchemaToConnectorToolParameters(schema: unknown): ConnectorToolParameter[] {
  if (!isRecord(schema)) return [];
  const objectSchema = parameterObjectSchema(schema);
  if (!isRecord(objectSchema.properties)) return [];
  const required = new Set(Array.isArray(objectSchema.required) ? objectSchema.required.filter((value): value is string => typeof value === 'string') : []);
  return Object.entries(objectSchema.properties).map(([name, value]) => {
    const property = isRecord(value) ? value : {};
    return {
      name,
      label: typeof property.title === 'string' && property.title.length > 0 ? property.title : formatLabel(name),
      type: schemaType(property, schema),
      description: typeof property.description === 'string' ? property.description : '',
      required: required.has(name)
    };
  });
}
