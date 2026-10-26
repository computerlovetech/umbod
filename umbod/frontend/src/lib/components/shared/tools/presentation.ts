export type ToolParameter = {
  name: string;
  label: string;
  type: string;
  description: string;
  required: boolean;
};

export type ToolOutputSchemaState =
  | { status: 'available'; schema: Record<string, unknown> }
  | { status: 'not-declared' };
