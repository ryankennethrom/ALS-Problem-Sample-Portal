export type ToastKind = 'success' | 'error';

export type ToastDetail = {
  id?: string;
  kind: ToastKind;
  message: string;
  duration?: number;
};

const EVENT_NAME = 'eps:toast';
const PENDING_KEY = 'eps_pending_toast';

function makeId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function showToast(kind: ToastKind, message: string, duration = 5000) {
  if (typeof window === 'undefined') return;
  const detail: ToastDetail = { id: makeId(), kind, message, duration };
  window.dispatchEvent(new CustomEvent<ToastDetail>(EVENT_NAME, { detail }));
}

export function toastSuccess(message: string, duration?: number) {
  showToast('success', message, duration);
}

export function toastError(message: string, duration?: number) {
  showToast('error', message, duration);
}

export function queueToastForReload(kind: ToastKind, message: string) {
  if (typeof window === 'undefined') return;
  sessionStorage.setItem(PENDING_KEY, JSON.stringify({ id: makeId(), kind, message, duration: 5000 } satisfies ToastDetail));
}

export function consumeQueuedToast(): ToastDetail | null {
  if (typeof window === 'undefined') return null;
  const raw = sessionStorage.getItem(PENDING_KEY);
  if (!raw) return null;
  sessionStorage.removeItem(PENDING_KEY);
  try {
    return JSON.parse(raw) as ToastDetail;
  } catch {
    return null;
  }
}

export { EVENT_NAME as TOAST_EVENT_NAME };
