'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { microsoftMailStatus, type MicrosoftMailStatus } from '@/lib/microsoftMail';

type Role = 'lab_technician' | 'customer_service';
type User = {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  name: string;
  role: Role | '';
  role_label: string;
  needs_role: boolean;
  needs_email: boolean;
  is_admin: boolean;
};

export default function AccountPage() {
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [passwordSaved, setPasswordSaved] = useState('');
  const [changingPassword, setChangingPassword] = useState(false);
  const [microsoft, setMicrosoft] = useState<MicrosoftMailStatus | null>(null);
  const [microsoftBusy, setMicrosoftBusy] = useState(false);
  const [microsoftError, setMicrosoftError] = useState('');

  useEffect(() => { microsoftMailStatus().then(setMicrosoft).catch(() => setMicrosoft(null)); }, []);

  async function connectMicrosoft() {
    setMicrosoftBusy(true); setMicrosoftError('');
    try {
      const result = await api('/auth/microsoft/start/', { method: 'POST' });
      window.location.assign(result.authorization_url);
    } catch (error) {
      setMicrosoftError(error instanceof Error ? error.message : 'Unable to start Microsoft sign-in');
      setMicrosoftBusy(false);
    }
  }
  async function disconnectMicrosoft() {
    setMicrosoftBusy(true); setMicrosoftError('');
    try {
      await api('/auth/microsoft/disconnect/', { method: 'POST' });
      setMicrosoft(await microsoftMailStatus());
    } catch (error) { setMicrosoftError(error instanceof Error ? error.message : 'Unable to disconnect Microsoft'); }
    finally { setMicrosoftBusy(false); }
  }

  useEffect(() => {
    api('/auth/me/').then((u: User) => {
      setUser(u);
    }).catch(e => setError(e instanceof Error ? e.message : 'Failed to load account'));
  }, []);

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    setPasswordError('');
    setPasswordSaved('');

    if (newPassword !== confirmPassword) {
      setPasswordError('New password and confirmation do not match.');
      return;
    }
    if (newPassword.length < 12) {
      setPasswordError('New password must be at least 12 characters long.');
      return;
    }

    setChangingPassword(true);
    try {
      await api('/auth/me/password/', {
        method: 'POST',
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
          confirm_password: confirmPassword,
        }),
        successMessage: 'Password changed successfully.',
        errorMessage: 'Could not change password',
      });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setPasswordSaved('Password changed successfully.');
    } catch(e) {
      setPasswordError(e instanceof Error ? e.message : 'Failed to change password');
    } finally {
      setChangingPassword(false);
    }
  }

  return <div>
    <h1 className="page-heading">My Account</h1>
    <section className="panel panel-blue" style={{maxWidth: 680}}>
      <div className="panel-header">Account Details</div>
      <div className="panel-body stack">
        <div className="field"><label>Username</label><input className="input" value={user?.username || ''} readOnly /></div>
        <div className="field"><label>First Name</label><input className="input" value={user?.first_name || ''} readOnly /></div>
        <div className="field"><label>Last Name</label><input className="input" value={user?.last_name || ''} readOnly /></div>
        <div className="field"><label>ALS Email</label><input className="input" value={user?.email || 'Not assigned'} readOnly /></div>
        <div className="field"><label>Workflow Role</label><input className="input" value={user?.role_label || 'Not assigned'} readOnly /></div>
        <div className="field"><label>Administrator</label><input className="input" value={user?.is_admin ? 'Yes' : 'No'} readOnly /></div>
        <div className="muted result-meta">Only administrators can change workflow roles and ALS email addresses. {user?.is_admin ? 'Use Staff Accounts to manage these settings.' : 'Contact your administrator if your account details need updating.'}</div>
        {(user?.needs_email || user?.needs_role) && <div className="error">Your account is missing required details. Contact an administrator to assign your role and ALS email before using the tracker.</div>}
        {error && <div className="error">{error}</div>}
      </div>
    </section>

    <section className="panel panel-blue" style={{maxWidth: 680, marginTop: 18}}>
      <div className="panel-header">Microsoft 365 — Optional Email Connection</div>
      <div className="panel-body stack">
        <p>Connecting Microsoft 365 is optional. Your existing ALS Ticket Tracker login will keep working.</p>
        <div className="muted result-meta">{microsoft?.connected ? `Connected as ${microsoft.email}` : microsoft?.configured ? 'Microsoft 365 is available, but not connected.' : 'Not yet configured. ALS IT must register the app and provide its credentials.'}</div>
        {microsoft?.redirect_uri && <div className="field"><label>Microsoft Entra Web Redirect URI (for IT)</label><input className="input" readOnly value={microsoft.redirect_uri} onClick={e => e.currentTarget.select()} /></div>}
        {microsoftError && <div className="error" role="alert">{microsoftError}</div>}
        <div>{microsoft?.connected ? <button type="button" className="button secondary" disabled={microsoftBusy} onClick={disconnectMicrosoft}>Disconnect Microsoft 365</button>
          : <button type="button" className="button" disabled={microsoftBusy || !microsoft?.configured} onClick={connectMicrosoft}>Connect Microsoft 365</button>}</div>
        <p className="muted">When connected, mail can be submitted through Microsoft Graph with To and CC recipients, rather than opening Outlook. A successful response means Microsoft accepted the message, not necessarily that it was delivered.</p>
      </div>
    </section>

    <section className="panel panel-blue" style={{maxWidth: 680, marginTop: 18}}>
      <div className="panel-header">Change Password</div>
      <form className="panel-body stack" onSubmit={changePassword}>
        <div className="field">
          <label htmlFor="current-password">Current Password</label>
          <input
            id="current-password"
            className="input"
            type="password"
            autoComplete="current-password"
            value={currentPassword}
            onChange={e => setCurrentPassword(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="new-password">New Password</label>
          <input
            id="new-password"
            className="input"
            type="password"
            autoComplete="new-password"
            value={newPassword}
            onChange={e => setNewPassword(e.target.value)}
            minLength={12}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="confirm-password">Confirm New Password</label>
          <input
            id="confirm-password"
            className="input"
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={e => setConfirmPassword(e.target.value)}
            minLength={12}
            required
          />
        </div>
        <div className="muted result-meta">Use at least 12 characters. Your new password must be different from your current password.</div>
        {passwordError && <div className="error">{passwordError}</div>}
        {passwordSaved && <div className="success">{passwordSaved}</div>}
        <div><button className="button" disabled={changingPassword}>{changingPassword ? 'Changing…' : 'Change Password'}</button></div>
      </form>
    </section>
  </div>;
}
