'use client';
import { useEffect, useRef, useState } from 'react';
import { microsoftMailStatus, sendWithMicrosoft365, type MicrosoftEmail } from '@/lib/microsoftMail';

export function useMicrosoftConnection() {
  const [connected, setConnected] = useState(false);
  const [checked, setChecked] = useState(false);
  useEffect(() => {
    let valid = true;
    microsoftMailStatus()
      .then(value => { if (valid) setConnected(value.connected); })
      .catch(() => { if (valid) setConnected(false); })
      .finally(() => { if (valid) setChecked(true); });
    return () => { valid = false; };
  }, []);
  return { connected, checked };
}

type Props = { content: MicrosoftEmail; onAccepted: (sendKey: string) => void | Promise<void>; disabled?: boolean; label?: string };
/** Graph acceptance and application-side confirmation are separate operations. */
export default function MicrosoftSendButton({ content, onAccepted, disabled, label = 'Send Email' }: Props) {
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<'accepted'|'rejected'|''>('');
  const [error, setError] = useState('');
  const key = useRef('');

  async function finishAfterAcceptance() {
    try { await onAccepted(key.current); }
    catch (e) {
      setError('Microsoft accepted the email, but the tracker action could not be saved. Retry the tracker action without sending again. ' + (e instanceof Error ? e.message : ''));
    }
  }

  async function send() {
    if (sending || result === 'accepted') return;
    if (!key.current) key.current = crypto.randomUUID();
    setSending(true);
    setError('');
    try {
      const response = await sendWithMicrosoft365(content, key.current);
      if (response.status !== 'accepted') throw new Error('Microsoft did not accept this email.');
    } catch (e) {
      setResult('rejected');
      setError(e instanceof Error ? e.message : 'Email Not Sent');
      setSending(false);
      // A timeout can be ambiguous. Do not automatically submit a second email.
      return;
    }
    setResult('accepted');
    setSending(false);
    await finishAfterAcceptance();
  }

  return <>
    <button type="button" className="button" disabled={disabled || sending || result === 'accepted'} onClick={send}>
      {sending ? 'Sending…' : result === 'accepted' ? 'Email Sent — Accepted by Microsoft' : label}
    </button>
    {result === 'accepted' && <span className="success" role="status">Email Sent. Microsoft accepted it for sending; delivery can still fail.</span>}
    {result === 'accepted' && <button type="button" className="button secondary" disabled={disabled} onClick={() => void finishAfterAcceptance()}>Retry tracker update without re-sending</button>}
    {result === 'rejected' && <span className="error" role="alert">Email Not Sent / unconfirmed: {error} Check Outlook Sent Items before retrying.</span>}
    {result === 'accepted' && error && <span className="error" role="alert">{error}</span>}
  </>;
}
