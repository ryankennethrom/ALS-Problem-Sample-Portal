'use client';

import { FormEvent, useState } from 'react';
import { api } from '@/lib/api';

function SignInIcon() {
  return <svg className="login-button-icon" viewBox="0 0 24 24" aria-hidden="true">
    <circle cx="12" cy="7" r="3.2" />
    <path d="M5.5 20v-2.2A5.8 5.8 0 0 1 11.3 12h1.4a5.8 5.8 0 0 1 5.8 5.8V20" />
    <path d="M9 20v-4.2M15 20v-4.2" />
  </svg>;
}

export default function Login() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');

  async function request(e: FormEvent) {
    e.preventDefault();
    setError('');
    setSending(true);
    try {
      await api('/auth/request-link/', {
        method: 'POST',
        body: JSON.stringify({ email }),
        successMessage: 'Sign-in link sent.',
        errorMessage: 'Could not send sign-in link',
      });
      setSent(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed');
    } finally {
      setSending(false);
    }
  }

  return <div className="login-screen">
    <section className="login-card" aria-labelledby="login-title">
      <div className="login-brand-area">
        <img className="login-logo" src="/als-logo.png" alt="ALS" />
        <h1 id="login-title">Edmonton Problem<br />Sample Tracker</h1>
      </div>

      <div className="login-divider" />

      <div className="login-form-area">
        {!sent ? <>
          <p className="login-prompt">Sign in to start your session</p>
          <form className="login-stack" onSubmit={request}>
            <div className="login-field">
              <label htmlFor="login-email">Company email</label>
              <input
                id="login-email"
                className="login-input"
                type="email"
                required
                autoComplete="email"
                placeholder="name@alsglobal.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
              />
            </div>
            <button className="login-primary-button" type="submit" disabled={sending}>
              <SignInIcon />{sending ? 'Sending…' : 'Send Sign-In Link'}
            </button>
          </form>
        </> : <>
          <p className="login-prompt">Check your email</p>
          <p className="login-subprompt">
            We sent a secure sign-in link to <strong>{email}</strong>. The link expires in <strong>5 minutes</strong> and can only be used once.
          </p>
          <div className="login-stack">
            <button className="login-secondary-button" type="button" onClick={() => { setSent(false); setError(''); }}>
              Use another email
            </button>
          </div>
          <div className="login-dev-note">In local development, the full sign-in link appears in the Django terminal.</div>
        </>}

        {error && <div className="login-error" role="alert">{error}</div>}
      </div>
    </section>
  </div>;
}
