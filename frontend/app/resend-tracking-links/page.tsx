'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { ProblemTable } from '@/lib/problemTables';

type Ticket = {
  id: string; problem_number: number; table_name: string; current_workflow: string;
  reason: string; escalated_at: string; created_at: string;
};
type Queue = { enabled: boolean; count: number; page: number; page_size: number; results: Ticket[] };

function showDate(value: string) {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}

export default function ResendTrackingLinksPage() {
  const [tables, setTables] = useState<ProblemTable[]>([]);
  const [table, setTable] = useState('');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Queue | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    api('/problem-tables/').then(result => setTables(Array.isArray(result) ? result : result.results || []))
      .catch(() => {});
  }, []);
  useEffect(() => {
    const refresh = () => setRevision(value => value + 1);
    window.addEventListener('monthly-reports-checked', refresh);
    return () => window.removeEventListener('monthly-reports-checked', refresh);
  }, []);
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    const params = new URLSearchParams({page: String(page)});
    if (table) params.set('table', table);
    if (query) params.set('q', query);
    api(`/dashboard/resend-tracking-links/?${params.toString()}`)
      .then((result: Queue) => { if (active) setData(result); })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : 'Could not load the resend queue.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [page, table, query, revision]);

  return <div>
    <div className="page-toolbar"><div>
      <div className="eyebrow">Action Required</div>
      <h1 className="page-heading" style={{marginBottom: 2}}>Resend Tracking Links</h1>
      <div className="muted table-description">Follow Up Required tickets whose latest history activity is an automatic Client Email priority escalation.</div>
    </div></div>
    {data && !data.enabled ? <section className="panel" style={{padding: 20}}>
      Enable <strong>Make next priority email list as contact if no response after a duration</strong> in a Client Email column to use this queue.
    </section> : <>
      <section className="panel panel-blue search-panel" style={{marginBottom: 18}}>
        <form className="search-grid table-search-grid" onSubmit={event => {event.preventDefault(); setPage(1); setQuery(search.trim());}}>
          <div className="field"><label htmlFor="resend-table">Ticket table</label>
            <select id="resend-table" className="select" value={table} onChange={event => {setTable(event.target.value);setPage(1);}}>
              <option value="">All tables</option>
              {tables.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </div>
          <div className="field search-wide"><label htmlFor="resend-search">Search tickets</label>
            <input id="resend-search" className="input" value={search} onChange={event => setSearch(event.target.value)} placeholder="Ticket number or table" />
          </div>
          <div className="field"><label aria-hidden="true">&nbsp;</label><button className="button" type="submit">Search</button></div>
        </form>
      </section>
      {error && <div className="card error" role="alert" style={{marginBottom: 14}}>{error}</div>}
      <section className="panel data-grid-panel">
        <div className="panel-header"><strong>Resend Tracking Links</strong>
          <span className="muted" style={{marginLeft: 8}}>({loading && !data ? '…' : data?.count ?? 0} tickets)</span>
        </div>
        <div className="data-table-wrap"><table className="data-table">
          <thead><tr><th className="row-action-column" aria-label="Open ticket"></th><th>Ticket ID</th><th>Table</th><th>Current Workflow</th><th>Escalation reason</th><th>Escalated At</th></tr></thead>
          <tbody>
            {loading && <tr><td colSpan={6} className="empty-table">Loading tickets…</td></tr>}
            {!loading && !error && data?.results.length === 0 && <tr><td colSpan={6} className="empty-table">No tracking links currently need resending.</td></tr>}
            {!loading && data?.results.map(ticket => <tr key={ticket.id}>
              <td className="row-action-column"><Link className="row-open-link" href={`/problems/${ticket.id}`} title="Open ticket">›</Link></td>
              <td><Link className="table-link" href={`/problems/${ticket.id}`}>Ticket #{ticket.problem_number}</Link></td>
              <td>{ticket.table_name}</td>
              <td><span className="badge">{ticket.current_workflow}</span></td>
              <td style={{minWidth: 300, whiteSpace:'normal'}}>{ticket.reason}</td>
              <td>{showDate(ticket.escalated_at)}</td>
            </tr>)}
          </tbody>
        </table></div>
        {data && data.count > data.page_size && <div className="panel-body" style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
          <button className="button" type="button" disabled={loading || page === 1} onClick={() => setPage(value => value - 1)}>Previous</button>
          <span className="muted">Page {page} of {Math.ceil(data.count / data.page_size)}</span>
          <button className="button" type="button" disabled={loading || page * data.page_size >= data.count} onClick={() => setPage(value => value + 1)}>Next</button>
        </div>}
      </section>
    </>}
  </div>;
}
