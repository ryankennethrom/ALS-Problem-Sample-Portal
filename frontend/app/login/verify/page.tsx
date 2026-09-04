'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, setToken } from '@/lib/api';

type State = 'verifying' | 'error';

export default function VerifyLoginLink() {
  const router = useRouter();
  const verificationStarted = useRef(false);
  const [state, setState] = useState<State>('verifying');
  const [message, setMessage] = useState('Verifying your secure sign-in link…');

  useEffect(() => {
    // React Strict Mode intentionally re-runs effects in development. A login
    // link is single-use, so starting a second exchange would consume/fail the
    // same credential. Keep one exchange per mounted verification page.
    if (verificationStarted.current) return;
    verificationStarted.current = true;

    const params = new URLSearchParams(window.location.search);
    const token = params.get('token') || '';

    if (!token) {
      setState('error');
      setMessage('This sign-in link is missing or invalid.');
      return;
    }

    // Capture the credential first, then remove it from the visible URL/history.
    // The in-memory token is still used by the single verification request.
    window.history.replaceState(null, '', '/login/verify');

    api('/auth/verify-link/', {
      method: 'POST',
      body: JSON.stringify({ token }),
    }).then(data => {
      setToken(data.token);

      // Use a full browser redirect after a successful one-time exchange.
      // This guarantees the newly stored session is picked up by the portal
      // immediately and removes the verification page from browser history.
      window.location.replace(data.user?.needs_role ? '/account' : '/');
    }).catch(error => {
      setState('error');
      setMessage(error instanceof Error ? error.message : 'This sign-in link could not be verified.');
    });
  }, [router]);

  return <div className="login-screen">
    <section className="login-card" aria-labelledby="verify-title">
      <div className="login-brand-area">
        <img className="login-logo" src="/als-logo.png" alt="ALS" />
        <h1 id="verify-title">Edmonton Problem<br />Sample Tracker</h1>
      </div>
      <div className="login-divider" />
      <div className="login-form-area">
        <p className="login-prompt">{state === 'verifying' ? 'Signing you in' : 'Sign-in link unavailable'}</p>
        <p className="login-subprompt">{message}</p>
        {state === 'error' && <div className="login-stack">
          <button className="login-primary-button" type="button" onClick={() => router.replace('/login')}>Request a new sign-in link</button>
        </div>}
      </div>
    </section>
  </div>;
}
