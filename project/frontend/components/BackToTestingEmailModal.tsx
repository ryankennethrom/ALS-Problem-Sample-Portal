'use client';

import { useEffect, useRef, useState } from 'react';
import { invokeCustomerEmail, mailtoForCustomerEmail } from '@/lib/customerEmail';
import { api } from '@/lib/api';

export type TestingCustomerMessage = {
  message: string;
  signature: string;
  createdAt: string;
};

export type TestingEmailDetails = {
  problemNumber: number; tableName: string; containerId: string;
  trackingNumber: string; problemType: string; reasonForHold: string;
  customerMessages: TestingCustomerMessage[];
  ticketUrl: string;
};

type Props = {
  details?: TestingEmailDetails;
  problemNumbers?: number[];
  onConfirm: (sent: boolean, body: string, recipient: string, notSentReason?: string) => void;
  onCancel: () => void;
  busy: boolean;
  error: string;
};

export default function BackToTestingEmailModal({ details, problemNumbers, onConfirm, onCancel, busy, error }: Props) {
  const [recipient, setRecipient] = useState('');
  const [recipientError, setRecipientError] = useState('');
  const [additional, setAdditional] = useState('');
  const [seconds, setSeconds] = useState<number | null>(null);
  const [copied, setCopied] = useState('');
  const [showNotSentReason, setShowNotSentReason] = useState(false);
  const [notSentReason, setNotSentReason] = useState('Email unknown');
  const countdownEndsAt = useRef(0);
  useEffect(() => {
    let active = true;
    api('/email-templates/edmonton-recipient/')
      .then((data: { email: string }) => { if (active) setRecipient(data.email); })
      .catch(() => { if (active) setRecipientError('Could not load the NA.EDM recipient. Close and reopen this email preview.'); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (seconds === null || seconds === 0) return;

    const updateCountdown = () => {
      setSeconds(Math.max(0, Math.ceil((countdownEndsAt.current - Date.now()) / 1000)));
    };
    const timer = window.setInterval(updateCountdown, 200);
    updateCountdown();
    return () => window.clearInterval(timer);
  }, [seconds]);

  const isBulk = Boolean(problemNumbers?.length);
  const subject = isBulk
    ? `${problemNumbers!.length} Tickets - Back to Testing`
    : `Ticket #${details?.problemNumber || 0} - Back to Testing`;
  const lines = isBulk ? [
    'Hello NA.EDM,', '',
    `The following ${problemNumbers!.length} tickets are moving to Back to Testing. Please review their samples for retesting.`, '',
    `Ticket IDs: ${problemNumbers!.map(number => `#${number}`).join(', ')}`,
  ] : [
    'Hello NA.EDM,', '',
    `Ticket #${details?.problemNumber || 0} is moving to Back to Testing. Please review the sample for retesting.`, '',
    `Table: ${details?.tableName || 'Not provided'}`,
    `Container: ${details?.containerId || 'Not provided'}`,
    `ALS Sample Tracking Number: ${details?.trackingNumber || 'Not provided'}`,
    `Problem Type: ${details?.problemType || 'Not provided'}`,
    `Reason for Hold: ${details?.reasonForHold || 'Not provided'}`,
    '',
    `Ticket link: ${details?.ticketUrl || 'Not available'}`,
  ];
  if (!isBulk && details?.customerMessages?.length) {
    lines.push('', 'Customer messages:');
    details.customerMessages.forEach((customerMessage, index) => {
      const sentAt = customerMessage.createdAt
        ? new Date(customerMessage.createdAt).toLocaleString()
        : 'Time unavailable';
      const sender = customerMessage.signature || 'Customer';
      lines.push('', `${index + 1}. ${sender} — ${sentAt}`, customerMessage.message);
    });
  }
  if (additional.trim()) lines.push('', 'Additional details:', additional.trim());
  lines.push('', 'Regards,', 'ALS');
  const body = lines.join('\n');

  async function copy(text: string, what: string) {
    try { await navigator.clipboard.writeText(text); setCopied(`${what} copied`); }
    catch { setCopied('Could not copy automatically. Select the text and copy it manually.'); }
  }
  function proceed() {
    if (!recipient || body.length > 10000) return;
    countdownEndsAt.current = Date.now() + 5000;
    setSeconds(5);
    invokeCustomerEmail(mailtoForCustomerEmail({ to: [recipient], cc: [], subject, body }));
  }
  return <div className="email-confirm-overlay" role="presentation">
    <div className="email-confirm-dialog customer-email-preview" role="dialog" aria-modal="true" aria-labelledby="testing-email-title">
      <h2 id="testing-email-title">Notify NA.EDM: Back to Testing</h2>
      <p className="customer-email-company-reminder"><strong>Send this email from your ALS company email account.</strong> You can copy the address and message if your email application does not open.</p>
      <div className="customer-email-preview-content">
        <div className="customer-email-preview-heading"><strong>Recipient</strong><button type="button" className="button secondary" onClick={() => copy(recipient, 'Address')} disabled={!recipient}>Copy address</button></div>
        <div className="customer-email-addresses">To: {recipient || 'Loading address…'}</div>
        <div className="field"><label htmlFor="testing-email-extra">Additional details (optional)</label><textarea id="testing-email-extra" className="textarea" maxLength={2000} value={additional} onChange={event => setAdditional(event.target.value)} placeholder="Add instructions for the Edmonton team…" disabled={seconds !== null}/></div>
        <div className="customer-email-preview-heading"><strong>Email to send</strong><button type="button" className="button secondary" onClick={() => copy(`Subject: ${subject}\n\n${body}`, 'Email')}>Copy email</button></div>
        <div className="field"><label htmlFor="testing-email-subject">Subject</label><input id="testing-email-subject" className="input" readOnly value={subject}/></div>
        <div className="field"><label htmlFor="testing-email-body">Message</label><textarea id="testing-email-body" className="textarea customer-email-body" readOnly value={body}/></div>
      </div>
      {copied && <p className="muted customer-email-copy-status" role="status">{copied}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {body.length > 10000 && <p className="error" role="alert">The email is too long. Select fewer tickets.</p>}
      {recipientError && <p className="error" role="alert">{recipientError}</p>}
      {seconds !== null && <p className="customer-email-send-prompt" role="status">Send the email now{seconds > 0 ? `. You can confirm in ${seconds} second${seconds === 1 ? '' : 's'}.` : '.'}</p>}
      {showNotSentReason && <div className="field" style={{marginBottom: 16}}>
        <label htmlFor="testing-email-not-sent-reason">Why wasn&apos;t the email sent? <span aria-hidden="true">*</span></label>
        <textarea id="testing-email-not-sent-reason" className="textarea" required maxLength={500} autoFocus value={notSentReason} onChange={event => setNotSentReason(event.target.value)} disabled={busy} />
        {!notSentReason.trim() && <span className="error" role="alert">A reason is required.</span>}
      </div>}
      <div className="email-confirm-actions">
        {!showNotSentReason && seconds === null && <button type="button" className="button" onClick={proceed} disabled={busy || !recipient || body.length > 10000}>Proceed</button>}
        {!showNotSentReason && seconds === 0 && <button type="button" className="button" onClick={() => onConfirm(true, body, recipient)} disabled={busy}>{busy ? 'Saving…' : 'I sent the email'}</button>}
        {!showNotSentReason && seconds === 0 && <button type="button" className="button secondary" onClick={() => setShowNotSentReason(true)} disabled={busy}>{"I didn't send the email"}</button>}
        {showNotSentReason && <button type="button" className="button" onClick={() => onConfirm(false, body, recipient, notSentReason.trim())} disabled={busy || !notSentReason.trim()}>{busy ? 'Saving…' : 'Confirm email not sent'}</button>}
        {showNotSentReason && <button type="button" className="button secondary" onClick={() => setShowNotSentReason(false)} disabled={busy}>Back</button>}
        <button type="button" className="button secondary" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </div>
  </div>;
}
