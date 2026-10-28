'use client';

import { useState } from 'react';
import { CustomerEmailContent } from '@/lib/customerEmail';
import { useWebmailSendCountdown, WebmailOpeningStatus } from '@/components/useWebmailSendCountdown';

type Props = {
  recipients: string[];
  problemNumber: number;
  onSent: (message: CustomerEmailContent) => void;
  onCancel: () => void;
  busy?: boolean;
  error?: string;
};

export default function GeneralCustomerEmailModal({ recipients, problemNumber, onSent, onCancel, busy = false, error = '' }: Props) {
  const [subject, setSubject] = useState(`Ticket Ticket #${problemNumber}`);
  const [body, setBody] = useState(`Hello,\n\nI'm contacting you regarding ticket ticket #${problemNumber}.\n\nRegards,\nALS`);
  const { seconds, start } = useWebmailSendCountdown();
  const message: CustomerEmailContent = { to: recipients, cc: [], subject: subject.trim(), body: body.trim() };

  function openEmail() {
    if (!message.subject || !message.body || !recipients.length) return;
    start(message);
  }

  return <div className="email-confirm-overlay" role="presentation">
    <div className="email-confirm-dialog customer-email-preview" role="dialog" aria-modal="true" aria-labelledby="general-email-title">
      <h2 id="general-email-title">Email Customer</h2>
      <p className="customer-email-company-reminder"><strong>Send this message from your ALS company email account.</strong> This email does not include or activate a tracking link.</p>
      <div className="customer-email-preview-content">
        <div className="customer-email-addresses"><strong>To:</strong> {recipients.join('; ')}</div>
        <div className="field"><label htmlFor="general-email-subject">Subject</label><input id="general-email-subject" className="input" maxLength={500} required value={subject} onChange={event => { setSubject(event.target.value); }} disabled={busy || seconds !== null} /></div>
        <div className="field"><label htmlFor="general-email-body">Message</label><textarea id="general-email-body" className="textarea customer-email-body" maxLength={10000} required value={body} onChange={event => { setBody(event.target.value); }} disabled={busy || seconds !== null} /></div>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <WebmailOpeningStatus seconds={seconds} />
      <div className="email-confirm-actions">
        {seconds === null && <button type="button" className="button" onClick={openEmail} disabled={busy || !recipients.length || !message.subject || !message.body}>Send Email</button>}
        {seconds === 0 && <button type="button" className="button" onClick={() => onSent(message)} disabled={busy}>{busy ? 'Saving…' : 'I sent the email'}</button>}
        {seconds === 0 && <button type="button" className="button secondary" onClick={onCancel} disabled={busy}>{"I didn't send the email"}</button>}
        <button type="button" className="button secondary" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </div>
  </div>;
}
