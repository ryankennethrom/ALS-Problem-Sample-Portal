'use client';

import { useEffect, useRef, useState } from 'react';
import { CustomerEmailContent, invokeCustomerEmail, mailtoForCustomerEmail } from '@/lib/customerEmail';
import { useWebmailSendCountdown, WebmailOpeningStatus } from '@/components/useWebmailSendCountdown';

type Props = {
  content: CustomerEmailContent | null;
  onSent: () => void;
  onDidNotSend: (reason: string) => void;
  onCancel: () => void;
  busy?: boolean;
  error?: string;
  requireNotSentReason?: boolean;
  /** Skip the extra Send Email click after an explicit action has prepared this tracking-link draft. */
  autoStart?: boolean;
};

export default function CustomerEmailModal({ content, onSent, onDidNotSend, onCancel, busy = false, error = '', requireNotSentReason = true, autoStart = false }: Props) {
  const { seconds, start } = useWebmailSendCountdown();
  const [copied, setCopied] = useState('');
  const [showNotSentReason, setShowNotSentReason] = useState(false);
  const [notSentReason, setNotSentReason] = useState('Email unknown');
  const [showPreview, setShowPreview] = useState(!autoStart);
  const [launchError, setLaunchError] = useState('');
  const autoStartAttempted = useRef(false);

  // After the user's Create Ticket / Fits in container / Send Tracking Link action,
  // open the prepared draft without another confirmation window or Send Email click.
  // No tracking link is recorded as sent until staff confirms after the countdown.
  useEffect(() => {
    if (!autoStart || !content || autoStartAttempted.current) return;
    autoStartAttempted.current = true;
    try {
      start(content);
    } catch {
      setLaunchError('Web Mail could not be opened automatically. Use Try Opening Web Mail below.');
    }
  }, [autoStart, content, start]);

  async function copy(text: string, label: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(`${label} copied`);
    } catch {
      setCopied('Could not copy automatically. Select the text below and copy it manually.');
    }
  }

  function proceed() {
    if (!content) return;
    setLaunchError('');
    try {
      start(content);
    } catch {
      setLaunchError('Web Mail could not be opened. Please try again.');
    }
  }

  function retryWebmail() {
    if (!content) return;
    setLaunchError('');
    try {
      // A second, explicit click helps when the browser blocks an automatic mailto request.
      if (seconds === null) start(content);
      else invokeCustomerEmail(mailtoForCustomerEmail(content));
    } catch {
      setLaunchError('Web Mail could not be opened. Check your browser email-handler settings.');
    }
  }

  function didNotSend() {
    if (requireNotSentReason) {
      setShowNotSentReason(true);
      return;
    }
    onDidNotSend('User chose not to send the tracking-link email during ticket creation.');
  }

  const addresses = content ? [...content.to, ...content.cc] : [];
  return <div className="email-confirm-overlay" role="presentation">
    <div className="email-confirm-dialog customer-email-preview" role="dialog" aria-modal="true" aria-labelledby="email-preview-title" aria-describedby="email-preview-description">
      <h2 id="email-preview-title">{autoStart ? (seconds === 0 ? 'Confirm Tracking-Link Email' : 'Opening Web Mail') : 'Send Tracking Link'}</h2>
      <p id="email-preview-description" className="customer-email-company-reminder"><strong>Send this email from your ALS company email account.</strong> Confirm only after sending it from webmail.</p>
      {autoStart && content && <button type="button" className="button secondary" onClick={() => setShowPreview(value => !value)}>
        {showPreview ? 'Hide email details' : 'Review email details'}
      </button>}
      {content && showPreview ? <div className="customer-email-preview-content">
        <div className="customer-email-preview-heading"><strong>Recipients</strong><button type="button" className="button secondary" onClick={() => copy(addresses.join('; '), 'Addresses')}>Copy all addresses</button></div>
        <div className="customer-email-addresses"><strong>To:</strong> {content.to.join('; ') || '—'}{content.cc.length > 0 && <><br/><strong>Cc:</strong> {content.cc.join('; ')}</>}</div>
        <div className="customer-email-preview-heading"><strong>Email to send</strong><button type="button" className="button secondary" onClick={() => copy(`Subject: ${content.subject}\n\n${content.body}`, 'Email')}>Copy email</button></div>
        <div className="field"><label htmlFor="preview-subject">Subject</label><input id="preview-subject" className="input" readOnly value={content.subject} /></div>
        <div className="field"><label htmlFor="preview-body">Message</label><textarea id="preview-body" className="textarea customer-email-body" readOnly value={content.body} /></div>
      </div> : !content ? <p className="muted">Select a customer email address before sending a tracking link.</p> : null}
      {copied && <p className="muted customer-email-copy-status" role="status">{copied}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {launchError && <p className="error" role="alert">{launchError}</p>}
      <WebmailOpeningStatus seconds={seconds} />
      {seconds !== null && <p className="muted email-confirm-note">{requireNotSentReason ? 'The tracking link becomes active only after you confirm that the email was sent.' : 'The ticket and tracking link are created only after you choose whether the email was sent.'}</p>}
      {showNotSentReason && <div className="field" style={{marginBottom: 16}}>
        <label htmlFor="customer-email-not-sent-reason">Why wasn&apos;t the email sent? <span aria-hidden="true">*</span></label>
        <textarea id="customer-email-not-sent-reason" className="textarea" required maxLength={500} autoFocus value={notSentReason} onChange={event => setNotSentReason(event.target.value)} disabled={busy} />
        {!notSentReason.trim() && <span className="error" role="alert">A reason is required.</span>}
      </div>}
      <div className="email-confirm-actions">
        {!showNotSentReason && !autoStart && seconds === null && content && <button type="button" className="button" onClick={proceed} disabled={busy}>Send Email</button>}
        {!showNotSentReason && autoStart && launchError && seconds === null && content && <button type="button" className="button" onClick={retryWebmail} disabled={busy}>Try Opening Web Mail</button>}
        {!showNotSentReason && seconds === 0 && <button type="button" className="button" onClick={onSent} disabled={busy}>{busy ? 'Saving…' : 'I sent the email'}</button>}
        {!showNotSentReason && (seconds === 0 || !content) && <button type="button" className="button secondary" onClick={didNotSend} disabled={busy}>{"I didn't send the email"}</button>}
        {showNotSentReason && <button type="button" className="button" onClick={() => onDidNotSend(notSentReason.trim())} disabled={busy || !notSentReason.trim()}>{busy ? 'Saving…' : 'Confirm email not sent'}</button>}
        {showNotSentReason && <button type="button" className="button secondary" onClick={() => setShowNotSentReason(false)} disabled={busy}>Back</button>}
        {!showNotSentReason && autoStart && seconds === 0 && content && <button type="button" className="button secondary" onClick={retryWebmail} disabled={busy}>Open Web Mail again</button>}
        <button type="button" className="button secondary" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </div>
  </div>;
}
