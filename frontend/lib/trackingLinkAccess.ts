/** Hide customer tracking tokens from non-admin previews without changing the outgoing email. */
export function redactTrackingLinksForStaff(value: string): string {
  return value.replace(/(?:https?:\/\/[^\s\"<>]+)?\/track\/[A-Za-z0-9_-]+(?:\?[^\s\"<>]*)?/gi, '[Tracking link included in webmail draft]');
}
