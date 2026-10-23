'use client';

import { FormEvent, useEffect, useState } from 'react';
import { api, activeLabCode } from '@/lib/api';

type Lab = {
  id: number;
  name: string;
  code: string;
  references?: Record<string, number>;
  can_delete?: boolean;
  lab_notification_mode: string;
  lab_notification_emails: string[];
  customer_service_notification_mode: string;
  customer_service_notification_emails: string[];
};

export default function LabSettings() {
  const [config, setConfig] = useState<Lab | null>(null);
  const [labs, setLabs] = useState<Lab[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [newLab, setNewLab] = useState('');
  const [code, setCode] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState('');
  const [labAddresses, setLabAddresses] = useState('');
  const [csAddresses, setCsAddresses] = useState('');
  const all = activeLabCode() === 'ALL';

  async function refreshLabs() {
    const result = await api('/auth/labs/');
    setLabs(Array.isArray(result) ? result : []);
    window.dispatchEvent(new Event('tracker-labs-updated'));
  }

  useEffect(() => {
    let cancelled = false;
    api('/auth/labs/').then((result) => {
      if (!cancelled) setLabs(Array.isArray(result) ? result : []);
    }).catch(e => { if (!cancelled) setError(String(e)); });
    if (!all) {
      api('/auth/labs/notifications/').then((v: Lab) => {
        if (cancelled) return;
        setConfig(v);
        setLabAddresses(v.lab_notification_emails.join(', '));
        setCsAddresses(v.customer_service_notification_emails.join(', '));
      }).catch(e => { if (!cancelled) setError(String(e)); });
    }
    return () => { cancelled = true; };
  }, [all]);

  async function addLab(event: FormEvent) {
    event.preventDefault();
    setError(''); setNotice(''); setBusy(true);
    try {
      const created: Lab = await api('/auth/labs/', { method: 'POST', body: JSON.stringify({ name: newLab.trim(), code: code.trim().toUpperCase() }) });
      await refreshLabs();
      setNewLab(''); setCode('');
      setNotice(`Created ${created.name} (${created.code}).`);
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }

  async function renameLab(event: FormEvent, lab: Lab) {
    event.preventDefault();
    setError(''); setNotice(''); setBusy(true);
    try {
      const renamed: Lab = await api(`/auth/labs/${lab.id}/`, { method: 'PATCH', body: JSON.stringify({ name: editingName.trim() }) });
      await refreshLabs();
      setEditingId(null);
      setNotice(`Renamed lab to ${renamed.name}. Lab code ${lab.code} stays unchanged.`);
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }

  async function deleteLab(lab: Lab) {
    if (!window.confirm(`Delete ${lab.name} (${lab.code})? This can only succeed when the lab has no references. This action cannot be undone.`)) return;
    setError(''); setNotice(''); setBusy(true);
    try {
      await api(`/auth/labs/${lab.id}/`, { method: 'DELETE' });
      await refreshLabs();
      setNotice(`Deleted ${lab.name}.`);
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }

  async function save(event: FormEvent) {
    event.preventDefault(); if (!config) return;
    setNotice(''); setError(''); setBusy(true);
    try {
      const data = await api('/auth/labs/notifications/', { method: 'PUT', body: JSON.stringify({
        lab_notification_mode: config.lab_notification_mode,
        lab_notification_emails: labAddresses.split(/[;,\n]/).map(s => s.trim()).filter(Boolean),
        customer_service_notification_mode: config.customer_service_notification_mode,
        customer_service_notification_emails: csAddresses.split(/[;,\n]/).map(s => s.trim()).filter(Boolean),
      }) });
      setConfig(data);
      setNotice('Lab notification settings saved.');
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }

  return <div className="stack">
    <h1>Lab Settings</h1>
    <p className="muted">Manage lab names and notification recipients. Lab codes are permanent so existing container IDs remain stable.</p>
    {error && <p className="error" role="alert">{error}</p>}
    {notice && <p className="success" role="status">{notice}</p>}

    {all ? <>
      <section className="panel lab-management-panel">
        <h2>Manage Labs</h2>
        <p className="muted">Add labs, rename them, or delete an unused lab. Switching to a specific lab lets you configure its notifications and email templates.</p>
        <div className="lab-management-list">
          {labs.map(lab => {
            const references = Object.entries(lab.references || {});
            const canDelete = lab.can_delete === true;
            const editing = editingId === lab.id;
            return <div className="lab-management-item" key={lab.id}>
              <div className="lab-management-summary">
                <span className="lab-management-code">{lab.code}</span>
                <div className="lab-management-details">
                  <strong>{lab.name}</strong>
                  {references.length ? <span className="muted">In use: {references.map(([kind, count]) => `${kind} (${count})`).join(', ')}</span>
                    : <span className="muted">{canDelete ? 'Not referenced — safe to delete' : 'At least one lab must remain'}</span>}
                </div>
                <div className="lab-management-actions">
                  <button className="button secondary" type="button" disabled={busy} onClick={() => { setEditingId(editing ? null : lab.id); setEditingName(lab.name); setError(''); }}>
                    {editing ? 'Cancel' : 'Rename'}
                  </button>
                  <button className="button secondary" type="button" disabled={busy || !canDelete} onClick={() => void deleteLab(lab)} title={canDelete ? 'Delete unused lab' : 'Remove all lab references before deleting'}>Delete</button>
                </div>
              </div>
              {editing && <form className="lab-management-rename" onSubmit={event => void renameLab(event, lab)}>
                <label htmlFor={`rename-lab-${lab.id}`}>New lab name</label>
                <input id={`rename-lab-${lab.id}`} className="input" maxLength={100} required value={editingName} onChange={event => setEditingName(event.target.value)}/>
                <button className="button" disabled={busy || !editingName.trim() || editingName.trim() === lab.name}>Save name</button>
              </form>}
            </div>;
          })}
        </div>
      </section>
      <section className="panel lab-management-panel">
        <h2>Add Lab</h2>
        <form className="lab-create-form" onSubmit={addLab}>
          <label htmlFor="new-lab-name">Lab name
            <input id="new-lab-name" className="input" required maxLength={100} value={newLab} onChange={event => setNewLab(event.target.value)} placeholder="e.g. Calgary" />
          </label>
          <label htmlFor="new-lab-code">Permanent code (2–12 letters/numbers)
            <input id="new-lab-code" className="input" required minLength={2} maxLength={12} pattern="[A-Z0-9]{2,12}" value={code} onChange={event => setCode(event.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''))} placeholder="CGY" />
          </label>
          <button className="button" type="submit" disabled={busy || !newLab.trim() || code.length < 2}>Add Lab</button>
        </form>
      </section>
    </> : config && <form className="panel lab-management-panel" onSubmit={save}>
      <h2>{config.name} ({config.code}) — Notification routing</h2>
      {([['lab', '@Lab', 'lab_notification_mode', labAddresses, setLabAddresses], ['customer_service', '@CustomerService', 'customer_service_notification_mode', csAddresses, setCsAddresses]] as const).map((entry) => {
        const [key, label, modeKey, value, write] = entry;
        return <div key={key} className="field">
          <h3>{label}</h3>
          <label>Recipients from
            <select className="select" value={config[modeKey]} onChange={event => setConfig(v => v ? { ...v, [modeKey]: event.target.value } : v)}>
              <option value="staff">Staff accounts in this lab with this role</option>
              <option value="addresses">Specified email addresses</option>
            </select>
          </label>
          {config[modeKey] === 'addresses' && <label>Recipient addresses (comma or newline separated)
            <textarea className="input" rows={3} value={value} onChange={event => write(event.target.value)} placeholder="person@alsglobal.com" />
          </label>}
        </div>;
      })}
      <button className="button" disabled={busy}>Save Lab Settings</button>
    </form>}
  </div>;
}
