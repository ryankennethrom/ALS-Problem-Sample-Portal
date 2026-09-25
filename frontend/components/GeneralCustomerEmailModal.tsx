'use client';

import { useEffect, useRef, useState } from 'react';
import { CustomerEmailContent, invokeCustomerEmail, mailtoForCustomerEmail } from '@/lib/customerEmail';

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
  const [opened, setOpened] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const countdownEndsAt = useRef(0);
  const message: CustomerEmailContent = { to: recipients, cc: [], subject: subject.trim(), body: body.trim() };

  useEffect(() => {
    if (!opened || seconds === 0) return;
    const timer = window.setInterval(() => setSeconds(Math.max(0, Math.ceil((countdownEndsAt.current - Date.now()) / 1000))), 200);
    return () => window.clearInterval(timer);
  }, [opened, seconds]);

  function openEmail() {
    if (!message.subject || !message.body || !recipients.length) return;
    invokeCustomerEmail(mailtoForCustomerEmail(message));
    countdownEndsAt.current = Date.now() + 5000;
    setSeconds(5);
    setOpened(true);
  }

  return <div className="email-confirm-overlay" role="presentation">
    <div className="email-confirm-dialog customer-email-preview" role="dialog" aria-modal="true" aria-labelledby="general-email-title">
      <h2 id="general-email-title">Email Customer</h2>
      <p className="customer-email-company-reminder"><strong>Send this message from your ALS company email account.</strong> This email does not include or activate a tracking link.</p>
      <div className="customer-email-preview-content">
        <div className="customer-email-addresses"><strong>To:</strong> {recipients.join('; ')}</div>
        <div className="field"><label htmlFor="general-email-subject">Subject</label><input id="general-email-subject" className="input" maxLength={500} required value={subject} onChange={event => { setSubject(event.target.value); setOpened(false); }} disabled={busy} /></div>
        <div className="field"><label htmlFor="general-email-body">Message</label><textarea id="general-email-body" className="textarea customer-email-body" maxLength={10000} required value={body} onChange={event => { setBody(event.target.value); setOpened(false); }} disabled={busy} /></div>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {opened && <p className="customer-email-send-prompt" role="status">Send the email now{seconds > 0 ? `. You can confirm in ${seconds} second${seconds === 1 ? '' : 's'}.` : '.'}</p>}
      <div className="email-confirm-actions">
        <button type="button" className="button" onClick={openEmail} disabled={busy || !message.subject || !message.body}>{opened ? 'Open email app again' : 'Open email app'}</button>
        {opened && seconds === 0 && <button type="button" className="button" onClick={() => onSent(message)} disabled={busy}>{busy ? 'Saving…' : 'I sent the email'}</button>}
        <button type="button" className="button secondary" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </div>
  </div>;
}
