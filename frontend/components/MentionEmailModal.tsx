'use client';

import { useEffect, useRef, useState } from 'react';
import { invokeCustomerEmail, mailtoForCustomerEmail } from '@/lib/customerEmail';
import { useWebmailSendCountdown, WebmailOpeningStatus } from '@/components/useWebmailSendCountdown';

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
  const { seconds, start } = useWebmailSendCountdown();
  const [launchError, setLaunchError] = useState('');
  const [showPreview, setShowPreview] = useState(false);
  const launchAttempted = useRef(false);
  // The backend intentionally returns exactly one draft per follow-up. Keeping
  // the array prop preserves compatibility with the existing preview API.
  const current = emails[0];

  const recipients = current ? (current.recipients?.length
    ? current.recipients
    : current.email.split(',').map(value => value.trim()).filter(Boolean)) : [];
  const message = current ? { to: recipients, cc: [], subject: current.subject, body: current.body } : null;
  // Preparing a mentioned follow-up is already an explicit staff action.
  useEffect(() => {
    if (launchAttempted.current || !message || !recipients.length) return;
    launchAttempted.current = true;
    try { start(message); }
    catch { setLaunchError('Web Mail could not be opened automatically. Try opening it again.'); }
  }, [current, start]);

  function retryWebmail() {
    if (!message) return;
    setLaunchError('');
    try {
      if (seconds === null) start(message);
      else invokeCustomerEmail(mailtoForCustomerEmail(message));
    } catch { setLaunchError('Web Mail could not be opened. Check your email handler settings.'); }
  }

  if (!current) return null;

  return <div className="email-confirm-overlay" role="presentation">
    <div className="email-confirm-dialog customer-email-preview" role="dialog" aria-modal="true" aria-labelledby="mention-email-title">
      <h2 id="mention-email-title">{seconds === 0 ? 'Confirm Mention Email' : 'Opening Web Mail'}</h2>
      <p className="customer-email-company-reminder"><strong>This follow-up has not been saved yet.</strong> Send this one generated email from your ALS company email account before the mention is added.</p>
      <button type="button" className="button secondary" onClick={() => setShowPreview(current => !current)}>{showPreview ? 'Hide email details' : 'Review email details'}</button>
      {showPreview && <div className="customer-email-preview-content">
        <div className="customer-email-addresses"><strong>To:</strong> {(current.recipients || []).join(', ') || current.email}</div>
        <div className="customer-email-addresses"><strong>Mentions:</strong> {(current.mentions || []).join(', ')}</div>
        <div className="field"><label>Subject</label><input className="input" readOnly value={current.subject} /></div>
        <div className="field"><label>Message</label><textarea className="textarea customer-email-body" readOnly value={current.body} /></div>
        <div className="muted result-meta">The complete follow-up message and direct ticket link are included in this email.</div>
      </div>}
      {error && <p className="error" role="alert">{error}</p>}
      {launchError && <p className="error" role="alert">{launchError}</p>}
      <WebmailOpeningStatus seconds={seconds} />
      <div className="email-confirm-actions">
        {launchError && seconds === null && <button type="button" className="button" onClick={retryWebmail} disabled={busy}>Try Opening Web Mail</button>}
        {seconds === 0 && <button type="button" className="button" onClick={onComplete} disabled={busy}>{busy ? 'Saving…' : 'I sent the email'}</button>}
        {seconds === 0 && <button type="button" className="button secondary" onClick={onCancel} disabled={busy}>{"I didn't send the email"}</button>}
        {seconds === 0 && <button type="button" className="button secondary" onClick={retryWebmail} disabled={busy}>Open Web Mail again</button>}
        <button type="button" className="button secondary" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </div>
  </div>;
}
