/** Keep Selected replaces the current list; Delete Selected removes only checked addresses. */
export function resolveClientEmailSelection(
  currentEmails: string[], visibleEmails: string[], selectedKeys: ReadonlySet<string>, action: 'keep' | 'delete',
): string[] {
  if (!selectedKeys.size) return currentEmails;
  if (action === 'delete') return currentEmails.filter(email => !selectedKeys.has(email.toLowerCase()));
  const seen = new Set<string>();
  return visibleEmails.filter(email => {
    const key = email.toLowerCase();
    if (!selectedKeys.has(key) || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
