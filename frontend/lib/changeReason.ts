export function changeReasonHeaders(reason?: string | null) {
  const normalized = (reason || '').trim();
  return normalized ? { 'X-Change-Reason': normalized } : {};
}
