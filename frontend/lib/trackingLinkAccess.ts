/** Hide customer tracking tokens from non-admin previews without changing the outgoing email. */
export function redactTrackingLinksForStaff(value: string): string {
  return value.replace(/(?:https?:\/\/[^\s\"<>]+)?\/track\/[A-Za-z0-9_-]+(?:\?[^\s\"<>]*)?/gi, '[Tracking link included in webmail draft]');
}

/** Locate the public customer tracking URL in a generated email, if present. */
export function trackingLinkFromEmail(body: string): string | null {
  const match = body.match(/https?:\/\/[^\s<>"']+?\/track\/[A-Za-z0-9_-]+(?:\?[^\s<>"']*)?/i);
  return match ? match[0].replace(/[.,;!)]*$/, '') : null;
}
