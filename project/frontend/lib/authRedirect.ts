const LOGIN_PATH = '/login';

export function normalizeInternalReturnPath(value: string | null | undefined): string | null {
  if (!value) return null;
  const candidate = value.trim();
  if (!candidate || candidate.length > 4096 || !candidate.startsWith('/') || candidate.startsWith('//')) return null;

  try {
    const base = 'https://tracker.local';
    const parsed = new URL(candidate, base);
    if (parsed.origin !== base) return null;
    if (parsed.pathname === LOGIN_PATH || parsed.pathname.startsWith(`${LOGIN_PATH}/`)) return null;
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return null;
  }
}

export function currentReturnPath(): string | null {
  if (typeof window === 'undefined') return null;
  return normalizeInternalReturnPath(`${window.location.pathname}${window.location.search}${window.location.hash}`);
}

export function requestedReturnPath(): string | null {
  if (typeof window === 'undefined') return null;
  return normalizeInternalReturnPath(new URLSearchParams(window.location.search).get('next'));
}

export function loginUrl(returnPath: string | null | undefined): string {
  const target = normalizeInternalReturnPath(returnPath);
  return target ? `${LOGIN_PATH}?next=${encodeURIComponent(target)}` : LOGIN_PATH;
}

export function accountSetupUrl(returnPath: string | null | undefined): string {
  const target = normalizeInternalReturnPath(returnPath);
  return target ? `/account?next=${encodeURIComponent(target)}` : '/account';
}
