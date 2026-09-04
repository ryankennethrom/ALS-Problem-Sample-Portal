'use client';

import { useCallback, useRef, useState } from 'react';

type ChangeReasonRequest = {
  title?: string;
  message: string;
};

type PendingRequest = Required<Pick<ChangeReasonRequest, 'message'>> & {
  title: string;
};

export function useChangeReasonModal() {
  const [pending, setPending] = useState<PendingRequest | null>(null);
  const [reason, setReason] = useState('');
  const resolver = useRef<((value: string | null) => void) | null>(null);

  const requestChangeReason = useCallback((request: ChangeReasonRequest | string) => {
    const normalized: PendingRequest = typeof request === 'string'
      ? { title: 'Reason for change', message: request }
      : { title: request.title || 'Reason for change', message: request.message };

    return new Promise<string | null>(resolve => {
      if (resolver.current) resolver.current(null);
      resolver.current = resolve;
      setReason('');
      setPending(normalized);
    });
  }, []);

  function finish(value: string | null) {
    const resolve = resolver.current;
    resolver.current = null;
    setPending(null);
    setReason('');
    resolve?.(value);
  }

  const trimmed = reason.trim();
  const tooLong = trimmed.length > 1000;

  const changeReasonModal = pending ? (
    <div
      className="change-reason-overlay"
      role="presentation"
      onMouseDown={event => {
        if (event.target === event.currentTarget) finish(null);
      }}
    >
      <div className="change-reason-dialog" role="dialog" aria-modal="true" aria-labelledby="change-reason-title" aria-describedby="change-reason-description">
        <h2 id="change-reason-title">{pending.title}</h2>
        <p id="change-reason-description" className="change-reason-copy">{pending.message}</p>
        <div className="field change-reason-field">
          <label htmlFor="change-reason-input">Reason</label>
          <textarea
            id="change-reason-input"
            className="textarea"
            autoFocus
            rows={5}
            maxLength={1001}
            value={reason}
            onChange={event => setReason(event.target.value)}
            placeholder="Describe why this change is being made…"
          />
          <div className={`change-reason-counter ${tooLong ? 'error-text' : 'muted'}`}>{trimmed.length}/1000</div>
          {tooLong && <div className="error-text">The reason must be 1000 characters or fewer.</div>}
        </div>
        <div className="change-reason-actions">
          <button type="button" className="button secondary" onClick={() => finish(null)}>Cancel</button>
          <button type="button" className="button secondary" onClick={() => finish('')}>Skip</button>
          <button type="button" className="button" disabled={!trimmed || tooLong} onClick={() => finish(trimmed)}>Continue</button>
        </div>
      </div>
    </div>
  ) : null;

  return { requestChangeReason, changeReasonModal };
}
