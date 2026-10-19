'use client';

import { useEffect, useRef } from 'react';

type Props = {
  containerId: string;
  onFits: () => void;
  onDifferent: () => void;
  onCreateNew: () => void;
  onDismiss: () => void;
};

/** A physical capacity check shown before preparing a new ticket in an existing container. */
export default function CreateTicketContainerFitModal({ containerId, onFits, onDifferent, onCreateNew, onDismiss }: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const dismissRef = useRef(onDismiss);
  useEffect(() => { dismissRef.current = onDismiss; }, [onDismiss]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    document.body.style.overflow = 'hidden';
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); dismissRef.current(); return; }
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const buttons = Array.from(dialogRef.current.querySelectorAll<HTMLButtonElement>('button:not([disabled])'));
      if (!buttons.length) return;
      if (event.shiftKey && document.activeElement === buttons[0]) { event.preventDefault(); buttons[buttons.length - 1].focus(); }
      else if (!event.shiftKey && document.activeElement === buttons[buttons.length - 1]) { event.preventDefault(); buttons[0].focus(); }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', onKeyDown);
      previousFocus?.focus();
    };
  }, []);

  return <div className="change-reason-overlay" role="presentation" onMouseDown={event => {
    if (event.target === event.currentTarget) onDismiss();
  }}>
    <div ref={dialogRef} className="change-reason-dialog reopen-container-dialog" role="dialog" aria-modal="true" aria-labelledby="create-container-fit-title" aria-describedby="create-container-fit-description">
      <h2 id="create-container-fit-title">Check container {containerId}</h2>
      <p id="create-container-fit-description" className="change-reason-copy" role="status">
        Please check container <strong>{containerId}</strong> first. If the ticket's samples don't fit, please use a different existing container or create a new one.
      </p>
      <p className="muted result-meta">Only confirm after checking the physical container. The ticket will be prepared after you confirm the fit.</p>
      <div className="change-reason-actions reopen-container-fit-actions">
        <button type="button" className="button" autoFocus onClick={onFits}>Fits in container {containerId}</button>
        <button type="button" className="button secondary" onClick={onDifferent}>Use a different existing container</button>
        <button type="button" className="button secondary" onClick={onCreateNew}>Create a new container</button>
      </div>
    </div>
  </div>;
}
