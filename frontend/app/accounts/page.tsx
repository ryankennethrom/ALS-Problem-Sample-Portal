'use client';

import { FormEvent, useEffect, useState } from 'react';
import { api } from '@/lib/api';

type Account = {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  name: string;
  role: string;
  role_label: string;
  is_admin: boolean;
  is_active: boolean;
  lab_id: number | null; lab_name: string;
};

type CurrentUser = {
  id: number;
};

type CreatedAccount = Account & { generated_password: string };
type ResetPasswordResult = Account & { generated_password: string };

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [currentUserId, setCurrentUserId] = useState<number | null>(null);
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newRole, setNewRole] = useState('lab_technician');
  const [labs, setLabs] = useState<Array<{id:number;name:string;code:string}>>([]);
  const [newLab, setNewLab] = useState('');
  const [editLab, setEditLab] = useState('');
  const [editingAccount, setEditingAccount] = useState<Account | null>(null);
  const [editEmail, setEditEmail] = useState('');
  const [editRole, setEditRole] = useState('lab_technician');
  const [created, setCreated] = useState<CreatedAccount | null>(null);
  const [resetResult, setResetResult] = useState<ResetPasswordResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [busyAction, setBusyAction] = useState('');
  const [error, setError] = useState('');
  const [copied, setCopied] = useState('');

  async function loadAccounts() {
    try {
      const [accountData, me]: [Account[], CurrentUser] = await Promise.all([
        api('/auth/accounts/'),
        api('/auth/me/'),
      ]);
      setAccounts(accountData);
      setCurrentUserId(me.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load accounts');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadAccounts(); api('/auth/labs/').then((v)=>{setLabs(v);setNewLab(String(v[0]?.id||''))}).catch(()=>{}); }, []);

  async function createAccount(e: FormEvent) {
    e.preventDefault();
    setError('');
    setCreated(null);
    setResetResult(null);
    setCopied('');
    setCreating(true);
    try {
      const result: CreatedAccount = await api('/auth/accounts/', {
        method: 'POST',
        body: JSON.stringify({ first_name: firstName, last_name: lastName, email: newEmail.trim().toLowerCase(), role: newRole, lab_id: Number(newLab) }),
        successMessage: 'Account created successfully.',
        errorMessage: 'Could not create account',
      });
      setCreated(result);
      setFirstName('');
      setLastName('');
      setNewEmail('');
      setNewRole('lab_technician');
      await loadAccounts();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create account');
    } finally {
      setCreating(false);
    }
  }

  function startEditAccount(account: Account) {
    setEditingAccount(account);
    setEditEmail(account.email || '');
    setEditRole(account.role || 'lab_technician');
    setEditLab(String(account.lab_id || ''));
    setError('');
  }

  async function saveAccountDetails(e: FormEvent) {
    e.preventDefault();
    if (!editingAccount) return;
    setError('');
    setBusyAction(`profile-${editingAccount.id}`);
    try {
      const updated: Account = await api(`/auth/accounts/${editingAccount.id}/profile/`, {
        method: 'PATCH',
        body: JSON.stringify({ email: editEmail.trim().toLowerCase(), role: editRole, lab_id: Number(editLab) }),
        successMessage: `Account details updated for ${editingAccount.name}.`,
        errorMessage: 'Could not update account details',
      });
      setAccounts(current => current.map(item => item.id === updated.id ? updated : item));
      setEditingAccount(null);
      if (updated.id === currentUserId) window.location.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update account details');
    } finally {
      setBusyAction('');
    }
  }

  async function setAdministrator(account: Account, isAdmin: boolean) {
    if (account.id === currentUserId) return;
    const message = isAdmin
      ? `Make ${account.name} an administrator? They will be able to create and manage staff accounts.`
      : `Remove administrator access from ${account.name}? Their existing login sessions will be revoked.`;
    if (!window.confirm(message)) return;

    setError('');
    setResetResult(null);
    setCopied('');
    const actionKey = `admin-${account.id}`;
    setBusyAction(actionKey);
    try {
      const updated: Account = await api(`/auth/accounts/${account.id}/admin/`, {
        method: 'PATCH',
        body: JSON.stringify({ is_admin: isAdmin }),
        successMessage: isAdmin ? `${account.name} is now an administrator.` : `Administrator access removed from ${account.name}.`,
        errorMessage: 'Could not update administrator access',
      });
      setAccounts(current => current.map(item => item.id === updated.id ? updated : item));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update administrator access');
    } finally {
      setBusyAction('');
    }
  }

  async function resetPassword(account: Account) {
    if (account.id === currentUserId) return;
    if (!window.confirm(`Reset the password for ${account.name}? Their current password will stop working and all of their existing login sessions will be revoked.`)) return;

    setError('');
    setCreated(null);
    setResetResult(null);
    setCopied('');
    const actionKey = `reset-${account.id}`;
    setBusyAction(actionKey);
    try {
      const result: ResetPasswordResult = await api(`/auth/accounts/${account.id}/reset-password/`, {
        method: 'POST',
        body: JSON.stringify({}),
        successMessage: `Password reset for ${account.name}.`,
        errorMessage: 'Could not reset password',
      });
      setResetResult(result);
      setAccounts(current => current.map(item => item.id === result.id ? result : item));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to reset password');
    } finally {
      setBusyAction('');
    }
  }

  async function deleteAccount(account: Account) {
    if (account.id === currentUserId) return;
    if (!window.confirm(`Delete ${account.name} (@${account.username})? This permanently removes the user account and cannot be undone.`)) return;

    setError('');
    setResetResult(null);
    setCopied('');
    const actionKey = `delete-${account.id}`;
    setBusyAction(actionKey);
    try {
      await api(`/auth/accounts/${account.id}/`, {
        method: 'DELETE',
        successMessage: `${account.name} was deleted.`,
        errorMessage: 'Could not delete account',
      });
      setAccounts(current => current.filter(item => item.id !== account.id));
      if (created?.id === account.id) setCreated(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete account');
    } finally {
      setBusyAction('');
    }
  }

  async function copy(label: string, value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(label);
    } catch {
      setCopied('');
    }
  }

  return <div>
    <div className="page-heading-row">
      <div>
        <h1 className="page-heading">Staff Accounts</h1>
        <div className="muted">Administrators assign each staff member an ALS email and workflow role. Staff cannot change these details themselves. Administrator access is managed separately.</div>
      </div>
    </div>

    <section className="panel panel-blue" style={{maxWidth: 760, marginBottom: 20}}>
      <div className="panel-header">Create Account</div>
      <form className="panel-body stack" onSubmit={createAccount}>
        <div className="field"><label htmlFor="new-first-name">First Name <span className="required-marker" aria-hidden="true"> *</span></label><input id="new-first-name" className="input" required maxLength={150} value={firstName} onChange={e => setFirstName(e.target.value)} /></div>
        <div className="field"><label htmlFor="new-last-name">Last Name <span className="required-marker" aria-hidden="true"> *</span></label><input id="new-last-name" className="input" required maxLength={150} value={lastName} onChange={e => setLastName(e.target.value)} /></div>
        <div className="field"><label htmlFor="new-email">ALS Email <span className="required-marker" aria-hidden="true"> *</span></label><input id="new-email" className="input" type="email" required placeholder="first.last@alsglobal.com" value={newEmail} onChange={e => setNewEmail(e.target.value)} /></div>
        <div className="field"><label htmlFor="new-role">Workflow Role <span className="required-marker" aria-hidden="true"> *</span></label><select id="new-role" className="select" required value={newRole} onChange={e => setNewRole(e.target.value)}><option value="lab_technician">Lab</option><option value="customer_service">Customer Service</option></select></div>
        <div className="field"><label htmlFor="new-lab">Associated lab *</label><select id="new-lab" className="select" required value={newLab} onChange={e=>setNewLab(e.target.value)}><option value="">Select lab</option>{labs.map(l=><option key={l.id} value={l.id}>{l.name}</option>)}</select></div>
        <div className="muted result-meta">The username is generated from the person&apos;s name, for example <strong>jane.smith</strong>. Duplicate names receive a numeric suffix.</div>
        <div><button className="button" disabled={creating}>{creating ? 'Creating…' : 'Create Account'}</button></div>
      </form>
    </section>

    {editingAccount && <section className="panel panel-blue" style={{maxWidth: 760, marginBottom: 20}}>
      <div className="panel-header">Edit Role and Email — {editingAccount.name}</div>
      <form className="panel-body stack" onSubmit={saveAccountDetails}>
        <div className="field"><label htmlFor="edit-email">ALS Email</label><input id="edit-email" className="input" type="email" required value={editEmail} onChange={e => setEditEmail(e.target.value)} /></div>
        <div className="field"><label htmlFor="edit-role">Workflow Role</label><select id="edit-role" className="select" required value={editRole} onChange={e => setEditRole(e.target.value)}><option value="lab_technician">Lab</option><option value="customer_service">Customer Service</option></select></div>
        <div className="field"><label htmlFor="edit-lab">Associated lab *</label><select id="edit-lab" className="select" required value={editLab} onChange={e=>setEditLab(e.target.value)}><option value="">Select lab</option>{labs.map(l=><option key={l.id} value={l.id}>{l.name}</option>)}</select></div>
        <div className="muted result-meta">Changing a role can change which Group fields the account belongs to. ALS email addresses must end in @alsglobal.com.</div>
        <div style={{display:'flex', gap:8, flexWrap:'wrap'}}><button className="button" disabled={Boolean(busyAction)} type="submit">{busyAction === `profile-${editingAccount.id}` ? 'Saving…' : 'Save Role and Email'}</button><button className="button secondary" type="button" disabled={Boolean(busyAction)} onClick={() => setEditingAccount(null)}>Cancel</button></div>
      </form>
    </section>}

    {created && <section className="panel" style={{maxWidth: 760, marginBottom: 20}}>
      <div className="panel-header">New Account Credentials</div>
      <div className="panel-body stack">
        <div className="success">Account created. Give these credentials to {created.name}. The generated password is only returned when the account is created.</div>
        <div className="field"><label>Username</label><div style={{display:'flex', gap:8}}><input className="input" readOnly value={created.username} /><button className="button secondary" type="button" onClick={() => copy('username', created.username)}>Copy</button></div></div>
        <div className="field"><label>Generated Random Password</label><div style={{display:'flex', gap:8}}><input className="input" readOnly value={created.generated_password} /><button className="button secondary" type="button" onClick={() => copy('password', created.generated_password)}>Copy</button></div></div>
        {copied && <div className="muted result-meta">Copied {copied}.</div>}
      </div>
    </section>}

    {resetResult && <section className="panel" style={{maxWidth: 760, marginBottom: 20}}>
      <div className="panel-header">Password Reset Credentials</div>
      <div className="panel-body stack">
        <div className="success">Password reset for {resetResult.name}. Their old password and existing login sessions no longer work. Give them the new password below.</div>
        <div className="field"><label>Username</label><div style={{display:'flex', gap:8}}><input className="input" readOnly value={resetResult.username} /><button className="button secondary" type="button" onClick={() => copy('username', resetResult.username)}>Copy</button></div></div>
        <div className="field"><label>New Random Password</label><div style={{display:'flex', gap:8}}><input className="input" readOnly value={resetResult.generated_password} /><button className="button secondary" type="button" onClick={() => copy('password', resetResult.generated_password)}>Copy</button></div></div>
        {copied && <div className="muted result-meta">Copied {copied}.</div>}
      </div>
    </section>}

    {error && <div className="error" style={{marginBottom: 16}}>{error}</div>}

    <section className="panel">
      <div className="panel-header">Accounts</div>
      <div className="panel-body">
        {loading ? <div className="muted">Loading accounts…</div> : accounts.length === 0 ? <div className="muted">No accounts found.</div> : <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>Name</th><th>Username</th><th>ALS Email</th><th>Workflow Role</th><th>Lab</th><th>Administrator</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>{accounts.map(account => {
              const isSelf = account.id === currentUserId;
              const adminBusy = busyAction === `admin-${account.id}`;
              const resetBusy = busyAction === `reset-${account.id}`;
              const deleteBusy = busyAction === `delete-${account.id}`;
              const anyBusy = Boolean(busyAction);
              return <tr key={account.id}>
                <td>{account.name}{isSelf && <div className="muted result-meta">Your account</div>}</td>
                <td>{account.username}</td>
                <td>{account.email || <span className="muted">Not set</span>}</td>
                <td>{account.role_label || 'Not selected'}</td><td>{account.lab_name || 'Unassigned'}</td>
                <td>{account.is_admin ? 'Yes' : 'No'}</td>
                <td>{account.is_active ? 'Active' : 'Disabled'}</td>
                <td>
                  <div style={{display:'flex', gap:8, flexWrap:'wrap'}}>
                    <button type="button" className="button secondary" disabled={anyBusy} onClick={() => startEditAccount(account)}>Edit Role / Email / Lab</button>
                    {!isSelf && <>
                    <button type="button" className="button secondary" disabled={anyBusy} onClick={() => void setAdministrator(account, !account.is_admin)}>
                      {adminBusy ? 'Updating…' : account.is_admin ? 'Remove Admin' : 'Make Admin'}
                    </button>
                    <button type="button" className="button secondary" disabled={anyBusy} onClick={() => void resetPassword(account)}>
                      {resetBusy ? 'Resetting…' : 'Reset Password'}
                    </button>
                    <button type="button" className="button danger" disabled={anyBusy} onClick={() => void deleteAccount(account)}>
                      {deleteBusy ? 'Deleting…' : 'Delete'}
                    </button>
                    </>}
                  </div>
                </td>
              </tr>;
            })}</tbody>
          </table>
        </div>}
      </div>
    </section>
  </div>;
}
