'use client';

import { useEffect, useRef, useState } from 'react';
import { invokeCustomerEmail, mailtoForCustomerEmail } from '@/lib/customerEmail';
import { useWebmailSendCountdown, WebmailOpeningStatus } from '@/components/useWebmailSendCountdown';

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
}: {
  email: CustomerHistoryReplyEmail;
  onSent: () => void;
  onCancel: () => void;
  busy?: boolean;
  error?: string;
}) {
  const { seconds, start } = useWebmailSendCountdown();
  const [launchError, setLaunchError] = useState('');
  const [showPreview, setShowPreview] = useState(false);
  const launchAttempted = useRef(false);

  // The staff already chose to reply and submitted the text. Open the finished
  // draft immediately, without another Send Email step.
  useEffect(() => {
    if (launchAttempted.current || !email.to.length) return;
    launchAttempted.current = true;
    try { start({ to: email.to, cc: email.cc || [], subject: email.subject, body: email.body }); }
    catch { setLaunchError('Web Mail could not be opened automatically. Try opening it again.'); }
  }, [email, start]);

  function retryWebmail() {
    setLaunchError('');
    const message = { to: email.to, cc: email.cc || [], subject: email.subject, body: email.body };
    try {
      if (seconds === null) start(message);
      else invokeCustomerEmail(mailtoForCustomerEmail(message));
    } catch { setLaunchError('Web Mail could not be opened. Check your email handler settings.'); }
  }

  return <div className="email-confirm-overlay" role="presentation">
    <div className="email-confirm-dialog customer-email-preview" role="dialog" aria-modal="true" aria-labelledby="customer-history-reply-email-title">
      <h2 id="customer-history-reply-email-title">{seconds === 0 ? 'Confirm Customer Reply' : 'Opening Web Mail'}</h2>
      <p className="customer-email-company-reminder"><strong>The staff reply has not been saved yet.</strong> Send this generated email from your ALS company email account, then confirm below.</p>
      <button type="button" className="button secondary" onClick={() => setShowPreview(current => !current)}>{showPreview ? 'Hide email details' : 'Review email details'}</button>
      {showPreview && <div className="customer-email-preview-content">
        <div className="customer-email-addresses"><strong>To:</strong> {email.to.join('; ') || '—'}</div>
        <div className="field"><label>Subject</label><input className="input" readOnly value={email.subject} /></div>
        <div className="field"><label>Message</label><textarea className="textarea customer-email-body" readOnly value={email.body} /></div>
        <div className="muted result-meta">The email includes the customer's original message, the staff reply, and a secure tracking link that opens “Message us about the issue.”</div>
      </div>}
      {error && <p className="error" role="alert">{error}</p>}
      {launchError && <p className="error" role="alert">{launchError}</p>}
      <WebmailOpeningStatus seconds={seconds} />
      <div className="email-confirm-actions">
        {launchError && seconds === null && <button type="button" className="button" onClick={retryWebmail} disabled={busy}>Try Opening Web Mail</button>}
        {seconds === 0 && <button type="button" className="button" onClick={onSent} disabled={busy}>{busy ? 'Saving…' : 'I sent the email'}</button>}
        {seconds === 0 && <button type="button" className="button secondary" onClick={onCancel} disabled={busy}>{"I didn't send the email"}</button>}
        {seconds === 0 && <button type="button" className="button secondary" onClick={retryWebmail} disabled={busy}>Open Web Mail again</button>}
        <button type="button" className="button secondary" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </div>
  </div>;
}
