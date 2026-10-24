'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

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
