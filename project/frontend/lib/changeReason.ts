export function changeReasonHeaders(reason?: string | null): Record<string, string> {
  const normalized = (reason || '').trim();
  const headers: Record<string, string> = {};
  if (normalized) headers['X-Change-Reason'] = normalized;
  return headers;
}
