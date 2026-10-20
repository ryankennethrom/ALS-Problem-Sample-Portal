'use client';

import { useEffect, useRef, useState } from 'react';
import { OUTLOOK_EMAIL_FALLBACK_EVENT, OUTLOOK_WEB_COMPOSE_URL_LIMIT, OutlookWebDraft } from '@/lib/customerEmail';

/** Copyable draft available for every email: Outlook may drop deep-link fields on login. */
export default function OutlookEmailManualCompose() {
  const [draft, setDraft] = useState<OutlookWebDraft | null>(null);
  const [copyStatus, setCopyStatus] = useState('');
  const previousFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const onDraft = (event: Event) => {
      previousFocus.current = document.activeElement as HTMLElement | null;
      setDraft((event as CustomEvent<OutlookWebDraft>).detail);
      setCopyStatus('');
    };
    window.addEventListener(OUTLOOK_EMAIL_FALLBACK_EVENT, onDraft);
    return () => window.removeEventListener(OUTLOOK_EMAIL_FALLBACK_EVENT, onDraft);
  }, []);

  function close() {
    setDraft(null);
    previousFocus.current?.focus();
  }

  useEffect(() => {
    if (!draft) return;
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') close(); };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [draft]);

  async function copy(value: string, name: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopyStatus(`${name} copied. Paste into the Outlook draft.`);
    } catch {
      setCopyStatus('Clipboard access was blocked. Select the text shown below and copy it manually.');
    }
  }

  if (!draft) return null;
  const requiresCcReview = draft.cc.length > 0;
  return <div className="outlook-manual-backdrop" role="presentation">
    <section className="outlook-manual-dialog" role="dialog" aria-modal="true" aria-labelledby="outlook-manual-title" aria-describedby="outlook-manual-description">
      <div className="outlook-manual-heading">
        <h2 id="outlook-manual-title">Check your email draft</h2>
        <button type="button" className="button secondary" onClick={close} aria-label="Close email instructions">Close</button>
      </div>
      <p id="outlook-manual-description">
        {draft.manualBody
          ? <>The full email exceeds the tracker&apos;s safe link length. <strong>It has NOT opened automatically.</strong> Copy the missing content below, then open the email draft. {draft.headersPrefilled ? 'To, Cc and Subject are included in the shortened link; the body must be pasted.' : 'Some recipients or the subject may also need to be pasted.'}</>
          : <>The tracker sent a <code>mailto:</code> link to your browser&apos;s registered email handler. If you configured Outlook Webmail as that handler, it should open a draft with To, Cc, Subject and Body. <strong>Verify all fields before sending.</strong></>}
      </p>
      {requiresCcReview && <p className="muted"><strong>Distributor Cc recipients:</strong> {draft.cc.join('; ')}. These are included in the email link; confirm they appear in the Cc field before sending. Use Copy Cc if your email handler omitted them.</p>}
      <p className="muted">This uses your browser&apos;s <code>mailto:</code> handler. If Outlook Webmail is not configured as the handler, your browser may open another mail app instead. Sign in to Outlook Webmail first and configure it as the protocol handler in your browser&apos;s settings (Chrome: Site settings → Protocol handlers; Edge: Cookies and site permissions → Protocol handlers). Corporate policies may require IT assistance.</p>
      {draft.manualBody && <p className="muted">Complete encoded mailto link: {draft.fullLinkLength.toLocaleString()} characters. Tracker safety limit: {OUTLOOK_WEB_COMPOSE_URL_LIMIT.toLocaleString()} characters. No email content was discarded from this preview.</p>}
      <div className="outlook-manual-fields">
        <label htmlFor="outlook-manual-to">To</label>
        <div className="outlook-manual-copy"><input className="input" id="outlook-manual-to" value={draft.to.join('; ')} readOnly /><button type="button" className="button secondary" onClick={() => copy(draft.to.join('; '), 'To recipients')}>Copy To</button></div>
        {requiresCcReview && <><label htmlFor="outlook-manual-cc"><strong>Cc — confirm these addresses in Outlook</strong></label><div className="outlook-manual-copy"><input className="input" id="outlook-manual-cc" value={draft.cc.join('; ')} readOnly /><button type="button" className="button" onClick={() => copy(draft.cc.join('; '), 'Cc recipients')}>Copy Cc recipients</button></div></>}
        <label htmlFor="outlook-manual-subject">Subject</label>
        <div className="outlook-manual-copy"><input className="input" id="outlook-manual-subject" value={draft.subject} readOnly /><button type="button" className="button secondary" onClick={() => copy(draft.subject, 'Subject')}>Copy subject</button></div>
        <label htmlFor="outlook-manual-body">Message body — copy if Outlook did not prefill it</label>
        <textarea className="textarea outlook-manual-body" id="outlook-manual-body" value={draft.body} readOnly rows={9} />
      </div>
      {copyStatus && <p role="status" className="muted">{copyStatus}</p>}
      <div className="outlook-manual-actions">
        <button type="button" className="button" onClick={() => copy(draft.body, 'Message body')}>Copy full message</button>
        <a className="button secondary" href={draft.link}>{draft.manualBody ? 'Open email draft' : 'Open email draft again'}</a>
        <button type="button" className="button secondary" onClick={close}>Done</button>
      </div>
      <p className="muted">Email links only prepare a draft; they do not send it. {requiresCcReview ? 'If Cc is empty in the draft, expand the Cc field and paste the addresses above. ' : ''}Check To, Cc, Subject, and Body before sending, then confirm “I sent the email” in the tracker only after you actually send it.</p>
    </section>
  </div>;
}
