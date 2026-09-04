'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { ProblemTable } from '@/lib/problemTables';

export default function TablesPage() {
  const [tables, setTables] = useState<ProblemTable[]>([]);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [ptDays, setPtDays] = useState(30);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  async function load() {
    const data = await api('/problem-tables/');
    setTables(Array.isArray(data) ? data : (data.results || []));
  }
  useEffect(() => { load().catch(e => setError(e instanceof Error ? e.message : 'Failed')); }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault(); setSaving(true); setError('');
    try {
      await api('/problem-tables/', {method:'POST', body:JSON.stringify({name, description, pt_days: ptDays}), successMessage:'Problem sample table created successfully.', errorMessage:'Could not create problem sample table'});
      setName(''); setDescription(''); setPtDays(30); await load();
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to create table'); }
    finally { setSaving(false); }
  }

  return <div>
    <h1 className="page-heading">Problem Sample Tables</h1>
    <div className="two-col tables-layout">
      <section className="panel panel-blue">
        <div className="panel-header">Existing Tables</div>
        <div className="table-card-list">
          {tables.map(t => <Link href={`/tables/${t.id}`} className="table-card-row" key={t.id}>
            <div><div className="result-title">{t.name} {t.is_default && <span className="badge blue">Default</span>}</div><div className="muted result-meta">{t.description || 'No description'}</div></div>
            <div className="table-stats"><span>{t.row_count} rows</span><span>Expiration: {t.pt_days === 0 ? 'Immediate' : `${t.pt_days} day${t.pt_days === 1 ? '' : 's'}`}</span><span>{Math.max(0, t.columns.filter(c => !c.is_system).length)} custom columns</span></div>
          </Link>)}
        </div>
      </section>
      <section className="panel">
        <div className="panel-header">Add Problem Sample Table</div>
        <form className="panel-body stack" onSubmit={create}>
          <div className="field"><label>Table name</label><input className="input" value={name} onChange={e=>setName(e.target.value)} required placeholder="e.g. Wear Debris Problem Samples"/></div>
          <div className="field"><label>Description</label><textarea className="textarea" value={description} onChange={e=>setDescription(e.target.value)} placeholder="What is this table used for?"/></div>
          <div className="field"><label>Problem Sample Expiration Period (days)</label><input className="input" type="number" min={0} max={3650} value={ptDays} onChange={e=>{ const value = Number(e.target.value); setPtDays(Number.isFinite(value) ? Math.min(3650, Math.max(0, value)) : 0); }} required/><div className="muted result-meta">How many days a sample remains in Automatically Disposed before becoming disposal-eligible. The countdown restarts each time that status is entered. Enter 0 for immediate eligibility. Default: 30 days.</div></div>
          <div className="muted result-meta">Every table starts with one built-in column: an auto-incrementing Problem ID. Add only the columns that table needs. Use the Fixed Value column type for values that should be constant across every row.</div>
          {error && <div className="error">{error}</div>}
          <div><button className="button" disabled={saving}>{saving ? 'Creating…' : '+ Add Table'}</button></div>
        </form>
      </section>
    </div>
  </div>;
}
