'use client';

import { useEffect, useId, useRef, useState } from 'react';

export default function ColumnInfo({ text, label }: { text?: string; label: string }) {
  const explanation = String(text || '').trim();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLSpanElement>(null);
  const rawId = useId();
  const tooltipId = `column-info-${rawId.replace(/[^a-zA-Z0-9_-]/g, '')}`;

  useEffect(() => {
    if (!open) return;

    function onPointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false);
    }

    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  if (!explanation) return null;

  return <span
    className={`column-info ${open ? 'column-info-open' : ''}`}
    ref={rootRef}
    onMouseEnter={() => setOpen(true)}
    onMouseLeave={() => setOpen(false)}
  >
    <button
      type="button"
      className="column-info-button"
      aria-label={`About ${label}`}
      aria-expanded={open}
      aria-describedby={open ? tooltipId : undefined}
      title={explanation}
      onFocus={() => setOpen(true)}
      onClick={event => {
        event.preventDefault();
        event.stopPropagation();
        setOpen(current => !current);
      }}
    >i</button>
    {open && <span id={tooltipId} className="column-info-popover" role="tooltip">{explanation}</span>}
  </span>;
}
