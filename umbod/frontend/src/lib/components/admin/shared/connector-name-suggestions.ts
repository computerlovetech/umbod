export function suggestedToolNamePrefix(displayName: string): string {
  return displayName.replace(/[^a-zA-Z0-9_-]+/g, '_').replace(/^_+|_+$/g, '') || 'connector';
}

export function suggestedConnectorId(displayName: string): string {
  return displayName.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}
