export function connectorInitials(label: string): string {
  const words = label.trim().split(/\s+/).filter(Boolean);

  if (words.length > 1) {
    return words.slice(0, 2).map((word) => word[0]).join('').toUpperCase();
  }

  return (words[0] ?? '?').slice(0, 2).toUpperCase();
}
