'use client';

import { useEffect, useRef, useState } from 'react';
import { CustomerEmailContent, invokeCustomerEmail, mailtoForCustomerEmail } from '@/lib/customerEmail';

/** Request a draft only from the user's Send Email click; never treat opening as proof of delivery. */
export function useWebmailSendCountdown() {
  const [seconds, setSeconds] = useState<number | null>(null);
  const endsAt = useRef(0);

  useEffect(() => {
    if (seconds === null || seconds === 0) return;
    const tick = () => setSeconds(Math.max(0, Math.ceil((endsAt.current - Date.now()) / 1000)));
    const interval = window.setInterval(tick, 200);
    tick();
    return () => window.clearInterval(interval);
  }, [seconds]);

  function start(message: CustomerEmailContent) {
    if (seconds !== null || endsAt.current) return;
    const link = mailtoForCustomerEmail(message);
    endsAt.current = Date.now() + 5000;
    setSeconds(5);
    try {
      invokeCustomerEmail(link);
    } catch (error) {
      endsAt.current = 0;
      setSeconds(null);
      throw error;
    }
  }

  function reset() {
    endsAt.current = 0;
    setSeconds(null);
  }

  return { seconds, start, reset };
}

export function WebmailOpeningStatus({ seconds }: { seconds: number | null }) {
  if (seconds === null) return null;
  return <p className="customer-email-send-prompt" role="status" aria-live="polite">
    {seconds > 0
      ? `Opening Web Mail — ${seconds} second${seconds === 1 ? '' : 's'} remaining…`
      : 'Web Mail was requested. Confirm only after you actually send the email.'}
  </p>;
}
