'use client';

import { useEffect, useState } from 'react';
import { useWebmailSendCountdown, WebmailOpeningStatus } from '@/components/useWebmailSendCountdown';
import { api } from '@/lib/api';
import { rackRemovalReminder } from '@/lib/rackRemovalReminder';

export type TestingCustomerMessage = {
  message: string;
  signature: string;
  createdAt: string;
};

export type TestingEmailBatchSample = {
  problemNumber: number;
  tableName: string;
  containerId: string;
  trackingNumber: string;
};

export type TestingEmailDetails = {
  problemNumber: number; tableName: string; containerId: string;
  trackingNumber: string; problemType: string; reasonForHold: string;
  customerMessages: TestingCustomerMessage[];
  ticketUrl: string;
};

type Props = {
  details?: TestingEmailDetails;
  batchSamples?: TestingEmailBatchSample[];
  showRackReminder?: boolean;
  onConfirm: (sent: boolean, body: string, recipient: string, notSentReason?: string) => void;
  onCancel: () => void;
  busy: boolean;
  error: string;
};

export default function BackToTestingEmailModal({ details, batchSamples, showRackReminder = true, onConfirm, onCancel, busy, error }: Props) {
  const [recipient, setRecipient] = useState('');
  const [recipientError, setRecipientError] = useState('');
  const [additional, setAdditional] = useState('');
  const { seconds, start } = useWebmailSendCountdown();
  const [copied, setCopied] = useState('');
  const [showNotSentReason, setShowNotSentReason] = useState(false);
  const [notSentReason, setNotSentReason] = useState('Email unknown');
  useEffect(() => {
    let active = true;
    api('/email-templates/edmonton-recipient/')
      .then((data: { email: string }) => { if (active) setRecipient(data.email); })
      .catch(() => { if (active) setRecipientError('Could not load the NA.EDM recipient. Close and reopen this email preview.'); });
    return () => { active = false; };
  }, []);

  const isBulk = Boolean(batchSamples?.length);
  const count = batchSamples?.length || 0;
  const subject = isBulk
    ? `${count} Ticket${count === 1 ? '' : 's'} - Back to Testing`
    : `Ticket #${details?.problemNumber || 0} - Back to Testing`;
  const lines = isBulk ? [
    'Hello NA.EDM,', '',
    `Please review these ${count} ticket${count === 1 ? '' : 's'} and their samples for retesting:`, '',
    ...batchSamples!.map(sample =>
      `- Ticket #${sample.problemNumber} | Table: ${sample.tableName || 'Not provided'} | Container: ${sample.containerId || 'Not provided'} | ALS #: ${sample.trackingNumber || 'Not provided'}`
    ),
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
    // Guard against a fast double click launching two drafts for one batch.
    if (!recipient || body.length > 10000 || seconds !== null) return;
    start({ to: [recipient], cc: [], subject, body });
  }
  return <div className="email-confirm-overlay" role="presentation">
    <div className="email-confirm-dialog customer-email-preview" role="dialog" aria-modal="true" aria-labelledby="testing-email-title">
      <h2 id="testing-email-title">Notify NA.EDM: Back to Testing</h2>
      {showRackReminder && <p className="rack-removal-warning" role="alert"><strong>Before moving {isBulk ? 'these tickets' : 'this ticket'} Back to testing:</strong> {rackRemovalReminder(count || 1)}</p>}
      <p className="customer-email-company-reminder"><strong>Send this email from your ALS company email account.</strong> {isBulk ? `One combined email will cover all ${count} selected tickets. ` : ''}You can copy the address and message if Outlook webmail does not open.</p>
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
      <WebmailOpeningStatus seconds={seconds} />
      {showNotSentReason && <div className="field" style={{marginBottom: 16}}>
        <label htmlFor="testing-email-not-sent-reason">Why wasn&apos;t the email sent? <span aria-hidden="true">*</span></label>
        <textarea id="testing-email-not-sent-reason" className="textarea" required maxLength={500} autoFocus value={notSentReason} onChange={event => setNotSentReason(event.target.value)} disabled={busy} />
        {!notSentReason.trim() && <span className="error" role="alert">A reason is required.</span>}
      </div>}
      <div className="email-confirm-actions">
        {!showNotSentReason && seconds === null && <button type="button" className="button" onClick={proceed} disabled={busy || !recipient || body.length > 10000}>Send Email</button>}
        {!showNotSentReason && seconds === 0 && <button type="button" className="button" onClick={() => onConfirm(true, body, recipient)} disabled={busy}>{busy ? 'Saving…' : 'I sent the email'}</button>}
        {!showNotSentReason && seconds === 0 && <button type="button" className="button secondary" onClick={() => setShowNotSentReason(true)} disabled={busy}>{"I didn't send the email"}</button>}
        {showNotSentReason && <button type="button" className="button" onClick={() => onConfirm(false, body, recipient, notSentReason.trim())} disabled={busy || !notSentReason.trim()}>{busy ? 'Saving…' : 'Confirm email not sent'}</button>}
        {showNotSentReason && <button type="button" className="button secondary" onClick={() => setShowNotSentReason(false)} disabled={busy}>Back</button>}
        <button type="button" className="button secondary" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </div>
  </div>;
}
