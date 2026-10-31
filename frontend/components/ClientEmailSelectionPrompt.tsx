'use client';

import { useEffect, useRef } from 'react';

type Props = {
  selectedCount: number;
  fieldCount: number;
  onKeep: () => void;
  onDelete: () => void;
  onCancel: () => void;
};

/** Gate ticket creation and saving when client-email checkboxes have not been committed. */
export default function ClientEmailSelectionPrompt({ selectedCount, fieldCount, onKeep, onDelete, onCancel }: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef(onCancel);
  useEffect(() => { cancelRef.current = onCancel; }, [onCancel]);
  useEffect(() => {
    const lastFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); cancelRef.current(); return; }
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const buttons = Array.from(dialogRef.current.querySelectorAll<HTMLButtonElement>('button:not([disabled])'));
      if (!buttons.length) return;
      if (event.shiftKey && document.activeElement === buttons[0]) { event.preventDefault(); buttons[buttons.length - 1].focus(); }
      else if (!event.shiftKey && document.activeElement === buttons[buttons.length - 1]) { event.preventDefault(); buttons[0].focus(); }
    };
    document.addEventListener('keydown', handler);
    return () => {
      document.body.style.overflow = oldOverflow;
      document.removeEventListener('keydown', handler);
      lastFocused?.focus();
    };
  }, []);

  return <div className="change-reason-overlay" role="presentation">
    <div ref={dialogRef} className="change-reason-dialog" role="dialog" aria-modal="true" aria-labelledby="client-email-selection-title" aria-describedby="client-email-selection-description">
      <h2 id="client-email-selection-title">Resolve selected client emails</h2>
      <p id="client-email-selection-description" className="change-reason-copy">
        You have {selectedCount} selected client email{selectedCount === 1 ? '' : 's'}{fieldCount > 1 ? ` across ${fieldCount} fields` : ''}, but you have not clicked <strong>Keep Selected</strong> or <strong>Delete Selected</strong>. Please select one of the following to continue saving.
      </p>
      <p className="muted result-meta"><strong>Keep Selected</strong> keeps only the checked email addresses in each affected field. <strong>Delete Selected</strong> removes the checked addresses. <strong>Cancel</strong> returns to the ticket without saving or changing the selection.</p>
      <div className="change-reason-actions">
        <button type="button" className="button" autoFocus onClick={onKeep}>Keep Selected &amp; Continue</button>
        <button type="button" className="button secondary" onClick={onDelete}>Delete Selected &amp; Continue</button>
        <button type="button" className="button secondary" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  </div>;
}
