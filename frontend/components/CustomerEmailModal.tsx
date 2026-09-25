'use client';

import { useEffect, useRef, useState } from 'react';
import { CustomerEmailContent, invokeCustomerEmail, mailtoForCustomerEmail } from '@/lib/customerEmail';

type Props = {
  content: CustomerEmailContent | null;
  onSent: () => void;
  onDidNotSend: (reason: string) => void;
  onCancel: () => void;
  busy?: boolean;
  error?: string;
  requireNotSentReason?: boolean;
};

export default function CustomerEmailModal({ content, onSent, onDidNotSend, onCancel, busy = false, error = '', requireNotSentReason = true }: Props) {
  const [seconds, setSeconds] = useState<number | null>(null);
  const countdownEndsAt = useRef(0);
  const [copied, setCopied] = useState('');
  const [showNotSentReason, setShowNotSentReason] = useState(false);
  const [notSentReason, setNotSentReason] = useState('Email unknown');

  useEffect(() => {
    if (seconds === null || seconds === 0) return;

    const updateCountdown = () => {
      setSeconds(Math.max(0, Math.ceil((countdownEndsAt.current - Date.now()) / 1000)));
    };
    const timer = window.setInterval(updateCountdown, 200);
    updateCountdown();
    return () => window.clearInterval(timer);
  }, [seconds]);

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
    countdownEndsAt.current = Date.now() + 5000;
    setSeconds(5);
    invokeCustomerEmail(mailtoForCustomerEmail(content));
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
      <h2 id="email-preview-title">Send Tracking Link</h2>
      <p id="email-preview-description" className="customer-email-company-reminder"><strong>Send this email from your ALS company email account.</strong> Review the recipients and message before sending.</p>
      {content ? <div className="customer-email-preview-content">
        <div className="customer-email-preview-heading"><strong>Recipients</strong><button type="button" className="button secondary" onClick={() => copy(addresses.join('; '), 'Addresses')}>Copy all addresses</button></div>
        <div className="customer-email-addresses"><strong>To:</strong> {content.to.join('; ') || '—'}{content.cc.length > 0 && <><br/><strong>Cc:</strong> {content.cc.join('; ')}</>}</div>
        <div className="customer-email-preview-heading"><strong>Email to send</strong><button type="button" className="button secondary" onClick={() => copy(`Subject: ${content.subject}\n\n${content.body}`, 'Email')}>Copy email</button></div>
        <div className="field"><label htmlFor="preview-subject">Subject</label><input id="preview-subject" className="input" readOnly value={content.subject} /></div>
        <div className="field"><label htmlFor="preview-body">Message</label><textarea id="preview-body" className="textarea customer-email-body" readOnly value={content.body} /></div>
      </div> : <p className="muted">Select a customer email address before sending a tracking link.</p>}
      {copied && <p className="muted customer-email-copy-status" role="status">{copied}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {seconds !== null && <p className="customer-email-send-prompt" role="status">Send the email now{seconds > 0 ? `. You can confirm in ${seconds} second${seconds === 1 ? '' : 's'}.` : '.'}</p>}
      {seconds !== null && <p className="muted email-confirm-note">{requireNotSentReason ? 'The tracking link becomes active only after you confirm that the email was sent.' : 'The ticket and tracking link are created only after you choose whether the email was sent.'}</p>}
      {showNotSentReason && <div className="field" style={{marginBottom: 16}}>
        <label htmlFor="customer-email-not-sent-reason">Why wasn&apos;t the email sent? <span aria-hidden="true">*</span></label>
        <textarea id="customer-email-not-sent-reason" className="textarea" required maxLength={500} autoFocus value={notSentReason} onChange={event => setNotSentReason(event.target.value)} disabled={busy} />
        {!notSentReason.trim() && <span className="error" role="alert">A reason is required.</span>}
      </div>}
      <div className="email-confirm-actions">
        {!showNotSentReason && seconds === null && content && <button type="button" className="button" onClick={proceed} disabled={busy}>Proceed</button>}
        {!showNotSentReason && seconds === 0 && <button type="button" className="button" onClick={onSent} disabled={busy}>{busy ? 'Saving…' : 'I sent the email'}</button>}
        {!showNotSentReason && (seconds === 0 || !content) && <button type="button" className="button secondary" onClick={didNotSend} disabled={busy}>{"I didn't send the email"}</button>}
        {showNotSentReason && <button type="button" className="button" onClick={() => onDidNotSend(notSentReason.trim())} disabled={busy || !notSentReason.trim()}>{busy ? 'Saving…' : 'Confirm email not sent'}</button>}
        {showNotSentReason && <button type="button" className="button secondary" onClick={() => setShowNotSentReason(false)} disabled={busy}>Back</button>}
        <button type="button" className="button secondary" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </div>
  </div>;
}
