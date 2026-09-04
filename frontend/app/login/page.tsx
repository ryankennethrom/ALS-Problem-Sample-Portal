'use client';

import { FormEvent, useState } from 'react';
import { api, setToken } from '@/lib/api';

type LoginUser = {
  id: number;
  username: string;
  name: string;
  needs_role: boolean;
};

type LoginResponse = {
  token: string;
  user: LoginUser;
};

function SignInIcon() {
  return <svg className="login-button-icon" viewBox="0 0 24 24" aria-hidden="true">
    <circle cx="12" cy="7" r="3.2" />
    <path d="M5.5 20v-2.2A5.8 5.8 0 0 1 11.3 12h1.4a5.8 5.8 0 0 1 5.8 5.8V20" />
    <path d="M9 20v-4.2M15 20v-4.2" />
  </svg>;
}

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [signingIn, setSigningIn] = useState(false);
  const [error, setError] = useState('');

  async function signIn(e: FormEvent) {
    e.preventDefault();
    setError('');
    setSigningIn(true);
    try {
      const data: LoginResponse = await api('/auth/login/', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
        errorMessage: 'Could not sign in',
      });
      setToken(data.token);
      window.location.replace(data.user.needs_role ? '/account' : '/');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Sign in failed');
    } finally {
      setSigningIn(false);
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
        <p className="login-prompt">Sign in to start your session</p>
        <form className="login-stack" onSubmit={signIn}>
          <div className="login-field">
            <label htmlFor="login-username">Username</label>
            <input
              id="login-username"
              className="login-input"
              type="text"
              required
              autoCapitalize="none"
              autoCorrect="off"
              autoComplete="username"
              placeholder="first.last"
              value={username}
              onChange={e => setUsername(e.target.value)}
            />
          </div>
          <div className="login-field">
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              className="login-input"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={e => setPassword(e.target.value)}
            />
          </div>
          <button className="login-primary-button" type="submit" disabled={signingIn}>
            <SignInIcon />{signingIn ? 'Signing in…' : 'Sign In'}
          </button>
        </form>
        <p className="login-subprompt">Accounts are created by a tracker administrator.</p>
        {error && <div className="login-error" role="alert">{error}</div>}
      </div>
    </section>
  </div>;
}
