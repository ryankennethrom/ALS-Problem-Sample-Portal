'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

type Role = 'lab_technician' | 'customer_service';
type User = { id:number; email:string; name:string; role:Role | ''; role_label:string; needs_role:boolean };

export default function AccountPage() {
  const [user, setUser] = useState<User | null>(null);
  const [role, setRole] = useState<Role>('lab_technician');
  const [error, setError] = useState('');
  const [saved, setSaved] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api('/auth/me/').then((u:User) => {
      setUser(u);
      if (u.role) setRole(u.role);
    }).catch(e => setError(e instanceof Error ? e.message : 'Failed to load account'));
  }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault(); setError(''); setSaved(''); setSaving(true);
    try {
      const updated:User = await api('/auth/me/', {method:'PATCH', body:JSON.stringify({role}), successMessage:'Role updated successfully.', errorMessage:'Could not update role'});
      setUser(updated);
      setRole(updated.role || 'lab_technician');
      setSaved('Role updated.');
    } catch(e) { setError(e instanceof Error ? e.message : 'Failed to update role'); }
    finally { setSaving(false); }
  }

  return <div>
    <h1 className="page-heading">My Account</h1>
    <section className="panel panel-blue" style={{maxWidth:620}}>
      <div className="panel-header">Account Details</div>
      <form className="panel-body stack" onSubmit={save}>
        <div className="field"><label>Email</label><input className="input" value={user?.email || ''} disabled/></div>
        <div className="field"><label>Role</label><select className="select" value={role} onChange={e=>setRole(e.target.value as Role)}><option value="lab_technician">Lab Technician</option><option value="customer_service">Customer Service</option></select></div>
        <div className="muted result-meta">Your role is used to identify your workflow context in the tracker. It is not an administrator/security permission.</div>
        {error && <div className="error">{error}</div>}
        {saved && <div className="success">{saved}</div>}
        <div><button className="button" disabled={saving}>{saving ? 'Saving…' : 'Save Role'}</button></div>
      </form>
    </section>
  </div>;
}
