'use client';

import { useEffect, useRef, useState } from 'react';
import { invokeCustomerEmail, mailtoForCustomerEmail } from '@/lib/customerEmail';

export type CustomerHistoryReplyEmail = {
  to: string[];
  cc: string[];
  subject: string;
  body: string;
  direct_url: string;
  customer_message: string;
};

export default function CustomerHistoryReplyEmailModal({
  email,
  onSent,
  onCancel,
  busy = false,
  error = '',
  launchedAt = 0,
}: {
  email: CustomerHistoryReplyEmail;
  onSent: () => void;
  onCancel: () => void;
  busy?: boolean;
  error?: string;
  launchedAt?: number;
}) {
  const [opened, setOpened] = useState(Boolean(launchedAt));
  const [seconds, setSeconds] = useState(launchedAt ? 5 : 0);
  const countdownEndsAt = useRef(launchedAt ? launchedAt + 5000 : 0);

  useEffect(() => {
    if (!opened || seconds === 0) return;
    const timer = window.setInterval(() => {
      setSeconds(Math.max(0, Math.ceil((countdownEndsAt.current - Date.now()) / 1000)));
    }, 200);
    return () => window.clearInterval(timer);
  }, [opened, seconds]);

  function openEmail() {
    invokeCustomerEmail(mailtoForCustomerEmail({
      to: email.to,
      cc: email.cc || [],
      subject: email.subject,
      body: email.body,
    }));
    countdownEndsAt.current = Date.now() + 5000;
    setSeconds(5);
    setOpened(true);
  }

  return <div className="email-confirm-overlay" role="presentation">
    <div className="email-confirm-dialog customer-email-preview" role="dialog" aria-modal="true" aria-labelledby="customer-history-reply-email-title">
      <h2 id="customer-history-reply-email-title">Send reply to customer</h2>
      <p className="customer-email-company-reminder"><strong>The staff reply has not been saved yet.</strong> Send this generated email from your ALS company email account, then confirm below.</p>
      <div className="customer-email-preview-content">
        <div className="customer-email-addresses"><strong>To:</strong> {email.to.join('; ') || '—'}</div>
        <div className="field"><label>Subject</label><input className="input" readOnly value={email.subject} /></div>
        <div className="field"><label>Message</label><textarea className="textarea customer-email-body" readOnly value={email.body} /></div>
        <div className="muted result-meta">The email includes the customer's original message, the staff reply, and a secure tracking link that opens “Message us about the issue.”</div>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {opened && <p className="customer-email-send-prompt" role="status">Send this email now{seconds > 0 ? `. You can confirm in ${seconds} second${seconds === 1 ? '' : 's'}.` : '.'}</p>}
      <div className="email-confirm-actions">
        <button type="button" className="button" onClick={openEmail} disabled={busy}>{opened ? 'Open email app again' : 'Open email app'}</button>
        {opened && seconds === 0 && <button type="button" className="button" onClick={onSent} disabled={busy}>{busy ? 'Saving…' : 'I sent this email — Save Reply'}</button>}
        <button type="button" className="button secondary" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </div>
  </div>;
}
