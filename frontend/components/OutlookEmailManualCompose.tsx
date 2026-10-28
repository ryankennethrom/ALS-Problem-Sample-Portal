'use client';

import { useEffect, useState } from 'react';
import { OUTLOOK_EMAIL_FALLBACK_EVENT, OutlookWebDraft } from '@/lib/customerEmail';

/**
 * Only show a non-modal fallback for oversized mailto links. Normal emails
 * open directly and stay in the sender's five-second confirmation workflow.
 * The shortened link omits the body, so we must keep that content copyable.
 */
export default function OutlookEmailManualCompose() {
  const [draft, setDraft] = useState<OutlookWebDraft | null>(null);
  const [copyStatus, setCopyStatus] = useState('');

  useEffect(() => {
    const onDraft = (event: Event) => {
      const next = (event as CustomEvent<OutlookWebDraft>).detail;
      // A normal email must never open a secondary prompt. Also dismiss an
      // old oversized-email warning if another, shorter email is launched.
      setDraft(next?.manualBody ? next : null);
      setCopyStatus('');
    };
    window.addEventListener(OUTLOOK_EMAIL_FALLBACK_EVENT, onDraft);
    return () => window.removeEventListener(OUTLOOK_EMAIL_FALLBACK_EVENT, onDraft);
  }, []);

  async function copy(value: string, name: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopyStatus(`${name} copied. Paste it into the webmail draft.`);
    } catch {
      setCopyStatus('Clipboard access was blocked. Select the text below and copy it manually.');
    }
  }

  if (!draft) return null;
  return <aside className="outlook-manual-notice" aria-label="Incomplete webmail draft warning">
    <div className="outlook-manual-heading">
      <strong>Complete the webmail draft</strong>
      <button type="button" className="button secondary" onClick={() => setDraft(null)} aria-label="Dismiss webmail warning">Dismiss</button>
    </div>
    <p role="alert"><strong>The email is too long for a browser link.</strong> Webmail was opened with a shortened draft. Its body was <strong>not included</strong>. Copy the complete message into webmail before sending.</p>
    {!draft.headersPrefilled && <p role="alert">Some recipient addresses or the subject may also be missing. Check and copy these fields as needed.</p>}
    <div className="outlook-manual-actions">
      <button type="button" className="button" onClick={() => copy(draft.body, 'Message body')}>Copy full message</button>
      <button type="button" className="button secondary" onClick={() => copy(draft.to.join('; '), 'To recipients')}>Copy To</button>
      {draft.cc.length > 0 && <button type="button" className="button secondary" onClick={() => copy(draft.cc.join('; '), 'Cc recipients')}>Copy Cc recipients</button>}
      {!draft.headersPrefilled && <button type="button" className="button secondary" onClick={() => copy(draft.subject, 'Subject')}>Copy Subject</button>}
      <a className="button secondary" href={draft.link}>Open webmail again</a>
    </div>
    {copyStatus && <p role="status" className="muted">{copyStatus}</p>}
    <details>
      <summary>Show complete message and recipient details</summary>
      <p><strong>To:</strong> {draft.to.join('; ') || '—'}</p>
      {draft.cc.length > 0 && <p><strong>Cc:</strong> {draft.cc.join('; ')}</p>}
      <p><strong>Subject:</strong> {draft.subject}</p>
      <textarea className="textarea outlook-manual-body" value={draft.body} readOnly rows={7} aria-label="Complete email body" />
    </details>
    <p className="muted">Opening webmail does not send an email. Confirm in the tracker only after actually sending it.</p>
  </aside>;
}
