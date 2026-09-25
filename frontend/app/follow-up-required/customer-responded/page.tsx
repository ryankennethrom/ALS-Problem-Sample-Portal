'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { ProblemTable } from '@/lib/problemTables';

type Ticket = {
  id: string; problem_number: number; table_name: string; status: string;
  current_workflow: string; customer_response: string; responded_at: string; created_at: string;
};
type TicketsResult = { count: number; page: number; page_size: number; results: Ticket[] };

function dateTime(value: string) {
  return new Date(value).toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}

export default function CustomerRespondedPage() {
  const [tables, setTables] = useState<ProblemTable[]>([]);
  const [table, setTable] = useState('');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<TicketsResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    api('/problem-tables/').then(result => setTables(Array.isArray(result) ? result : result.results || []))
      .catch(() => {});
  }, []);
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    const params = new URLSearchParams({ page: String(page) });
    if (table) params.set('table', table);
    if (query) params.set('q', query);
    api(`/dashboard/customer-responded/?${params}`)
      .then((result: TicketsResult) => { if (active) setData(result); })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : 'Could not load tickets.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [table, query, page]);

  return <div>
    <div className="page-toolbar"><div>
      <div className="eyebrow">Tickets</div>
      <h1 className="page-heading" style={{marginBottom: 2}}>New Customer Response</h1>
      <div className="muted table-description">Tickets whose latest history entry by a person is from the customer and whose workflow is eligible.</div>
    </div></div>
    <nav className="container-view-tabs" aria-label="CS Follow-Up views">
      <Link className="container-view-tab" href="/follow-up-required/tracking-not-sent">Tracking Not Sent</Link>
      <Link className="container-view-tab active" aria-current="page" href="/follow-up-required/customer-responded">New Customer Response</Link>
    </nav>
    <section className="panel panel-blue search-panel" style={{marginBottom: 18}}>
      <form className="search-grid table-search-grid" onSubmit={event => { event.preventDefault(); setPage(1); setQuery(search.trim()); }}>
        <div className="field"><label htmlFor="responded-table">Ticket table</label>
          <select id="responded-table" className="select" value={table} onChange={event => { setTable(event.target.value); setPage(1); }}>
            <option value="">All tables</option>
            {tables.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </div>
        <div className="field search-wide"><label htmlFor="responded-search">Search tickets</label>
          <input id="responded-search" className="input" value={search} onChange={event => setSearch(event.target.value)} placeholder="Ticket number, table, status, workflow…" />
        </div>
        <div className="field"><label aria-hidden="true">&nbsp;</label><button className="button" type="submit">Search</button></div>
      </form>
    </section>
    {error && <div className="card error" role="alert" style={{marginBottom: 14}}>{error}</div>}
    <section className="panel data-grid-panel">
      <div className="panel-header"><strong>New Customer Response</strong>
        <span className="muted" style={{marginLeft: 8}}>({loading && !data ? '…' : data?.count ?? 0} ticket{data?.count === 1 ? '' : 's'})</span>
      </div>
      <div className="data-table-wrap"><table className="data-table">
        <thead><tr><th className="row-action-column" aria-label="Open ticket"></th><th>Ticket ID</th><th>Table</th><th>Status</th><th>Current Workflow</th><th>Customer Response</th><th>Responded At</th><th>Date Created</th></tr></thead>
        <tbody>
          {loading && <tr><td colSpan={8} className="empty-table">Loading tickets…</td></tr>}
          {!loading && !error && data?.results.length === 0 && <tr><td colSpan={8} className="empty-table">No customer responses found.</td></tr>}
          {!loading && data?.results.map(ticket => <tr key={ticket.id}>
            <td className="row-action-column"><Link className="row-open-link" href={`/problems/${ticket.id}`} title="Open ticket">›</Link></td>
            <td><Link className="table-link" href={`/problems/${ticket.id}`}>Ticket #{ticket.problem_number}</Link></td>
            <td>{ticket.table_name}</td><td><span className="badge">{ticket.status || '—'}</span></td>
            <td><span className="badge">{ticket.current_workflow || '—'}</span></td>
            <td>{ticket.customer_response}</td><td>{dateTime(ticket.responded_at)}</td><td>{dateTime(ticket.created_at)}</td>
          </tr>)}
        </tbody>
      </table></div>
      {data && data.count > data.page_size && <div className="panel-body" style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
        <button type="button" className="button" disabled={loading || page === 1} onClick={() => setPage(p => p-1)}>Previous</button>
        <span className="muted">Page {page} of {Math.ceil(data.count / data.page_size)}</span>
        <button type="button" className="button" disabled={loading || page * data.page_size >= data.count} onClick={() => setPage(p => p+1)}>Next</button>
      </div>}
    </section>
  </div>;
}
