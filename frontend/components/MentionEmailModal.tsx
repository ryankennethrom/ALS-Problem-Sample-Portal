'use client';

import { useEffect, useRef, useState } from 'react';
import { invokeCustomerEmail, mailtoForCustomerEmail } from '@/lib/customerEmail';

export type MentionEmailDraft = {
  email: string;
  recipients: string[];
  mentions: string[];
  subject: string;
  body: string;
  direct_url: string;
};

export default function MentionEmailModal({
  emails,
  onComplete,
  onCancel,
  busy = false,
  error = '',
}: {
  emails: MentionEmailDraft[];
  onComplete: () => void;
  onCancel: () => void;
  busy?: boolean;
  error?: string;
}) {
  const [opened, setOpened] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const countdownEndsAt = useRef(0);
  // The backend intentionally returns exactly one draft per follow-up. Keeping
  // the array prop preserves compatibility with the existing preview API.
  const current = emails[0];

  useEffect(() => {
    if (!opened || seconds === 0) return;
    const timer = window.setInterval(() => {
      setSeconds(Math.max(0, Math.ceil((countdownEndsAt.current - Date.now()) / 1000)));
    }, 200);
    return () => window.clearInterval(timer);
  }, [opened, seconds]);

  if (!current) return null;

  function openEmail() {
    const recipients = current.recipients?.length
      ? current.recipients
      : current.email.split(',').map(value => value.trim()).filter(Boolean);
    invokeCustomerEmail(mailtoForCustomerEmail({
      to: recipients,
      cc: [],
      subject: current.subject,
      body: current.body,
    }));
    countdownEndsAt.current = Date.now() + 5000;
    setSeconds(5);
    setOpened(true);
  }

  return <div className="email-confirm-overlay" role="presentation">
    <div className="email-confirm-dialog customer-email-preview" role="dialog" aria-modal="true" aria-labelledby="mention-email-title">
      <h2 id="mention-email-title">Send mention email</h2>
      <p className="customer-email-company-reminder"><strong>This follow-up has not been saved yet.</strong> Send this one generated email from your ALS company email account before the mention is added.</p>
      <div className="customer-email-preview-content">
        <div className="customer-email-addresses"><strong>To:</strong> {(current.recipients || []).join(', ') || current.email}</div>
        <div className="customer-email-addresses"><strong>Mentions:</strong> {(current.mentions || []).join(', ')}</div>
        <div className="field"><label>Subject</label><input className="input" readOnly value={current.subject} /></div>
        <div className="field"><label>Message</label><textarea className="textarea customer-email-body" readOnly value={current.body} /></div>
        <div className="muted result-meta">The complete follow-up message and direct ticket link are included in this email.</div>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {opened && <p className="customer-email-send-prompt" role="status">Send this email now{seconds > 0 ? `. You can confirm in ${seconds} second${seconds === 1 ? '' : 's'}.` : '.'}</p>}
      <div className="email-confirm-actions">
        <button type="button" className="button" onClick={openEmail} disabled={busy}>{opened ? 'Open email app again' : 'Open email app'}</button>
        {opened && seconds === 0 && <button type="button" className="button" onClick={onComplete} disabled={busy}>{busy ? 'Saving…' : 'I sent this email — Save Follow Up'}</button>}
        <button type="button" className="button secondary" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </div>
  </div>;
}
