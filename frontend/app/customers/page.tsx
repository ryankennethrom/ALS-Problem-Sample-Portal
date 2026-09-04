'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
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

type CurrentUser = {
  id: number;
  is_admin: boolean;
};

type ImportHistoryItem = {
  id: number;
  filename: string;
  imported_at: string;
  row_count: number;
  days_ago: number;
  uploaded_by: {
    id: number | null;
    username: string;
    name: string;
  };
};

type CustomerOverview = {
  row_count: number;
  history_count: number;
  latest_upload: ImportHistoryItem | null;
  history: ImportHistoryItem[];
};

function formatNumber(value: number) {
  return new Intl.NumberFormat('en-CA').format(value);
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(new Date(value));
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('en-CA', {
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value));
}

function daysAgoLabel(days: number) {
  return `${days} day${days === 1 ? '' : 's'} ago`;
}

export default function Customers() {
  const router = useRouter();
  const [authorized, setAuthorized] = useState(false);
  const [loading, setLoading] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState('');
  const [q, setQ] = useState('');
  const [items, setItems] = useState<Customer[]>([]);
  const [overview, setOverview] = useState<CustomerOverview | null>(null);

  async function loadOverview() {
    const data: CustomerOverview = await api('/customers/overview/');
    setOverview(data);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me: CurrentUser = await api('/auth/me/');
        if (!me.is_admin) {
          router.replace('/');
          return;
        }
        if (!cancelled) setAuthorized(true);
        await loadOverview();
      } catch {
        router.replace('/');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [router]);

  async function upload() {
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    try {
      const d = await api('/customers/import/', {
        method: 'POST',
        body: fd,
        successMessage: 'Customer Export replaced successfully.',
        errorMessage: 'Customer import failed',
      });
      setMessage(`Replaced the previous customer directory (${formatNumber(d.replaced)} rows) with ${formatNumber(d.imported)} rows from ${d.filename}.`);
      setFile(null);
      await loadOverview();
      if (q) await search(q);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Import failed');
    }
  }

  async function search(v: string) {
    setQ(v);
    try {
      setItems(await api(`/customers/?q=${encodeURIComponent(v)}`));
    } catch {
      setItems([]);
    }
  }

  if (loading || !authorized) {
    return <div className="muted">Checking administrator access…</div>;
  }

  const latest = overview?.latest_upload || null;

  return <div>
    <div className="page-heading-row">
      <div>
        <h1 className="page-heading">Customers</h1>
        <div className="muted">Administrator-only customer directory and Customer Export management.</div>
      </div>
    </div>

    <div className="customer-summary-grid">
      <div className="customer-stat-card">
        <div className="customer-stat-label">Customer rows</div>
        <div className="customer-stat-value">{formatNumber(overview?.row_count || 0)}</div>
        <div className="muted result-meta">Rows in the current customer table</div>
      </div>
      <div className="customer-stat-card">
        <div className="customer-stat-label">Latest upload</div>
        <div className="customer-stat-value customer-stat-value-small">{latest ? daysAgoLabel(latest.days_ago) : 'No uploads yet'}</div>
        <div className="muted result-meta">{latest ? `${formatDate(latest.imported_at)} at ${formatTime(latest.imported_at)}` : 'Upload a Customer Export to begin the history.'}</div>
      </div>
    </div>

    <div className="customer-admin-layout">
      <div className="stack">
        <section className="panel panel-blue">
          <div className="panel-header">Customer Export</div>
          <div className="panel-body stack">
            <div className="muted">Upload a new Customer Export to completely replace the current customer directory.</div>
            <div className="muted result-meta">Supports .xlsx and .csv. The file is fully validated first; on success, the previous customer directory is discarded and recreated from this export. The upload record is retained in history. If replacement fails, the previous directory is kept.</div>
            <input
              key={file?.name || 'empty-file'}
              className="file-control"
              type="file"
              accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
              onChange={e => setFile(e.target.files?.[0] || null)}
            />
            <div><button className="button" disabled={!file} onClick={upload}>Upload Customer Export</button></div>
            {message && <div>{message}</div>}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <span>Customer Directory</span>
            <span className="history-count">{formatNumber(overview?.row_count || 0)} rows</span>
          </div>
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

      <aside className="panel customer-upload-history">
        <div className="panel-header">
          <span>Upload History</span>
          <span className="history-count">{overview?.history_count || 0} upload{overview?.history_count === 1 ? '' : 's'}</span>
        </div>
        <div className="panel-body customer-history-list">
          {!overview?.history.length ? <div className="muted">No Customer Export uploads recorded yet.</div> : overview.history.map((entry, index) => (
            <div className="customer-history-item" key={entry.id}>
              <div className="customer-history-topline">
                <div className="customer-history-file" title={entry.filename}>{entry.filename}</div>
                {index === 0 && <span className="customer-history-latest">Latest</span>}
              </div>
              <div className="customer-history-date">{formatDate(entry.imported_at)} at {formatTime(entry.imported_at)}</div>
              <div className="customer-history-meta">
                <span>{daysAgoLabel(entry.days_ago)}</span>
                <span>·</span>
                <span>{formatNumber(entry.row_count)} rows</span>
              </div>
              <div className="customer-history-uploader">
                Uploaded by {entry.uploaded_by.name}{entry.uploaded_by.username ? ` (@${entry.uploaded_by.username})` : ''}
              </div>
            </div>
          ))}
        </div>
      </aside>
    </div>
  </div>;
}
