'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';

type ContainerChoice = { mode: 'existing'; containerId: string } | { mode: 'new'; containerId: '' };

type Props = {
  ticketNumber: number;
  previousWorkflow: string;
  nextWorkflow: string;
  isInDumpingContainer: boolean;
  onCancel: () => void;
  onConfirm: (choice: ContainerChoice) => void;
};

/** A stable component: typing a Container ID must not remount the input. */
export default function ReopenContainerModal({
  ticketNumber,
  previousWorkflow,
  nextWorkflow,
  isInDumpingContainer,
  onCancel,
  onConfirm,
}: Props) {
  const [mode, setMode] = useState<'existing' | 'new'>('existing');
  const [containerId, setContainerId] = useState('');
  const [attempted, setAttempted] = useState(false);
  const missingContainer = mode === 'existing' && !containerId.trim();
  const dialogRef = useRef<HTMLFormElement>(null);
  const cancelRef = useRef(onCancel);
  useEffect(() => { cancelRef.current = onCancel; }, [onCancel]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    document.body.style.overflow = 'hidden';
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        cancelRef.current();
      }
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      ));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', onKeyDown);
      previousFocus?.focus();
    };
  }, []);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAttempted(true);
    if (isInDumpingContainer || missingContainer) return;
    if (mode === 'new') onConfirm({ mode: 'new', containerId: '' });
    else onConfirm({ mode: 'existing', containerId: containerId.trim() });
  }

  return (
    <div className="change-reason-overlay" role="presentation" onMouseDown={event => {
      if (event.target === event.currentTarget) onCancel();
    }}>
      <form ref={dialogRef} className="change-reason-dialog reopen-container-dialog" role="dialog" aria-modal="true" aria-labelledby="reopen-container-title" aria-describedby="reopen-container-description" onSubmit={submit}>
        <h2 id="reopen-container-title">Assign a container to reopen ticket #{ticketNumber}</h2>
        <p id="reopen-container-description" className="change-reason-copy">
          Moving from <strong>{previousWorkflow}</strong> to <strong>{nextWorkflow}</strong> requires a physical container. Choose where the samples will go before saving the ticket.
        </p>
        {isInDumpingContainer && <p role="alert" className="error">This ticket is in a dumping container. Undo that disposal before reopening it.</p>}
        <fieldset className="reopen-container-options" disabled={isInDumpingContainer}>
          <legend>Container selection</legend>
          <label className="check-label">
            <input type="radio" name="reopen-container-mode" checked={mode === 'existing'} onChange={() => { setMode('existing'); setAttempted(false); }} />
            Use an existing container
          </label>
          {mode === 'existing' && <div className="field reopen-container-input">
            <label htmlFor="reopen-existing-container">Existing Container ID</label>
            <input id="reopen-existing-container" className="input" type="text" value={containerId} onChange={event => setContainerId(event.target.value)} placeholder="e.g. PC-000123" autoFocus aria-invalid={attempted && missingContainer} aria-describedby="reopen-container-help" />
            <div className="muted result-meta" id="reopen-container-help">Enter the ID of an active container. It will be checked when you save.</div>
            {attempted && missingContainer && <div className="error" role="alert">Enter an existing Container ID.</div>}
          </div>}
          <label className="check-label">
            <input type="radio" name="reopen-container-mode" checked={mode === 'new'} onChange={() => { setMode('new'); setAttempted(false); }} />
            Create a new container
          </label>
          {mode === 'new' && <p className="muted result-meta reopen-container-new-note">A new Container ID will be generated when you save the ticket.</p>}
        </fieldset>
        <div className="change-reason-actions">
          <button type="button" className="button secondary" onClick={onCancel}>Cancel</button>
          <button type="submit" className="button" disabled={isInDumpingContainer}>Continue</button>
        </div>
      </form>
    </div>
  );
}
