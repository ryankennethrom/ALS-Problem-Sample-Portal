'use client';

import { FormEvent, useState } from 'react';
import { api } from '@/lib/api';

type User = {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  name: string;
  role: string;
  role_label: string;
  needs_role: boolean;
  needs_email: boolean;
  is_admin: boolean;
};

export default function RequiredEmailModal({ user, onSaved, onLogout }: { user: User; onSaved: (user: User) => void; onLogout: () => void }) {
  const [email, setEmail] = useState(user.email || '');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    const normalized = email.trim().toLowerCase();
    if (!normalized.endsWith('@alsglobal.com')) {
      setError('Enter your ALS email ending in @alsglobal.com.');
      return;
    }
    setSaving(true);
    try {
      const updated: User = await api('/auth/me/', {
        method: 'PATCH',
        body: JSON.stringify({ email: normalized }),
        successMessage: 'ALS email saved.',
        errorMessage: 'Could not save ALS email',
      });
      onSaved(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save ALS email');
    } finally {
      setSaving(false);
    }
  }

  return <div className="email-confirm-overlay" role="presentation">
    <div className="email-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="required-email-title">
      <h2 id="required-email-title">Set your ALS email</h2>
      <p>Your ALS email is required before you can use the tracker. It is used for staff mentions and mention notification emails.</p>
      <form className="stack" onSubmit={submit}>
        <div className="field">
          <label htmlFor="required-als-email">ALS email</label>
          <input
            id="required-als-email"
            className="input"
            type="email"
            autoComplete="email"
            placeholder="first.last@alsglobal.com"
            value={email}
            onChange={event => setEmail(event.target.value)}
            disabled={saving}
            required
            autoFocus
          />
          <div className="muted result-meta">Only @alsglobal.com addresses are accepted. Staff without an ALS email cannot be mentioned.</div>
        </div>
        {error && <div className="error" role="alert">{error}</div>}
        <div className="email-confirm-actions">
          <button className="button" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save ALS Email'}</button>
          <button className="button secondary" type="button" onClick={onLogout} disabled={saving}>Sign out</button>
        </div>
      </form>
    </div>
  </div>;
}
