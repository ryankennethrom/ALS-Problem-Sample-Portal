'use client';

import { useState } from 'react';
import { api } from '@/lib/api';

type Customer = {
  id: number;
  company_name: string;
  customer_type: string;
  email: string;
  external_customer_id: string;
  brand: string;
  city: string;
  state: string;
  primary_contact: string;
};

export default function Customers() {
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState('');
  const [q, setQ] = useState('');
  const [items, setItems] = useState<Customer[]>([]);

  async function upload() {
    if (!file) return;
    const fd = new FormData(); fd.append('file', file);
    try {
      const d = await api('/customers/import/', { method: 'POST', body: fd, successMessage:'Customer Export replaced successfully.', errorMessage:'Customer import failed' });
      setMessage(`Replaced the previous customer directory (${d.replaced} rows) with ${d.imported} rows from ${d.filename}.`);
    } catch (e) { setMessage(e instanceof Error ? e.message : 'Import failed'); }
  }
  async function search(v: string) {
    setQ(v);
    try { setItems(await api(`/customers/?q=${encodeURIComponent(v)}`)); } catch {}
  }

  return <div>
    <h1 className="page-heading">Customers</h1>
    <div className="stack">
      <section className="panel panel-blue">
        <div className="panel-header">Customer Export</div>
        <div className="panel-body stack">
          <div className="muted">Upload a new Customer Export to completely replace the current customer directory.</div>
          <div className="muted result-meta">Supports .xlsx and .csv. The file is fully validated first; on success, the previous customer directory is discarded and recreated from this export. If replacement fails, the previous directory is kept.</div>
          <input className="file-control" type="file" accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv" onChange={e => setFile(e.target.files?.[0] || null)}/>
          <div><button className="button" disabled={!file} onClick={upload}>Upload Customer Export</button></div>
          {message && <div>{message}</div>}
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">Customer Directory</div>
        <div className="panel-body" style={{paddingBottom:0}}>
          <input className="input" placeholder="Search company, customer ID, contact or email" value={q} onChange={e => search(e.target.value)}/>
        </div>
        <div style={{marginTop:12}}>
          {items.map(c => <div className="result" key={c.id}>
            <div className="result-title">{c.company_name}</div>
            <div>{c.email || 'No email'}{c.primary_contact ? ` · ${c.primary_contact}` : ''}</div>
            <div className="muted">{[c.external_customer_id && `CoyId ${c.external_customer_id}`, c.customer_type, c.brand, c.city, c.state].filter(Boolean).join(' · ')}</div>
          </div>)}
          {!!q && !items.length && <div className="empty-message muted">No customers found</div>}
        </div>
      </section>
    </div>
  </div>;
}
