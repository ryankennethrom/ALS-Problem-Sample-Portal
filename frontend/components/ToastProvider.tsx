'use client';

import { useCallback, useEffect, useState } from 'react';
import { consumeQueuedToast, ToastDetail, TOAST_EVENT_NAME } from '@/lib/toast';

type ToastItem = Required<Pick<ToastDetail, 'id' | 'kind' | 'message'>> & { duration: number };

export default function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts(current => current.filter(item => item.id !== id));
  }, []);

  const addToast = useCallback((detail: ToastDetail) => {
    const item: ToastItem = {
      id: detail.id || `${Date.now()}-${Math.random()}`,
      kind: detail.kind,
      message: detail.message,
      duration: detail.duration ?? 5000,
    };
    setToasts(current => [...current, item].slice(-5));
  }, [dismiss]);

  useEffect(() => {
    const queued = consumeQueuedToast();
    if (queued) addToast(queued);

    const handler = (event: Event) => addToast((event as CustomEvent<ToastDetail>).detail);
    window.addEventListener(TOAST_EVENT_NAME, handler);
    return () => window.removeEventListener(TOAST_EVENT_NAME, handler);
  }, [addToast]);

  return <>
    {children}
    <div className="toast-stack" aria-live="polite" aria-atomic="false">
      {toasts.map(toast => <div key={toast.id} className={`app-toast app-toast-${toast.kind}`} role={toast.kind === 'error' ? 'alert' : 'status'}>
        <div className="toast-icon" aria-hidden="true">{toast.kind === 'success' ? '✓' : '!'}</div>
        <div className="toast-message">{toast.message}</div>
        <button className="toast-close" type="button" aria-label="Dismiss notification" onClick={() => dismiss(toast.id)}>×</button>
        <div
          className="toast-progress"
          aria-hidden="true"
          style={{ animationDuration: `${toast.duration}ms` }}
          onAnimationEnd={() => dismiss(toast.id)}
        />
      </div>)}
    </div>
  </>;
}
