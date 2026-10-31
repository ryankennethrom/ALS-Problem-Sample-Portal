'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

type Ticket = {
  id: string; problem_number: number; table_name: string; container_id: string;
  created_at: string;
};

export default function BackToTestingPage() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    api('/problem-samples/back-to-testing/')
      .then((rows: Ticket[]) => setTickets(Array.isArray(rows) ? rows : []))
      .catch(e => setError(e instanceof Error ? e.message : 'Could not load Back to Testing tickets.'))
      .finally(() => setLoading(false));
  }, []);
  return <div>
    <h1 className="page-heading">Back To Testing</h1>
    <p className="muted">Tickets that have been returned to testing. No notification email is required.</p>
    {error && <p className="error" role="alert">{error}</p>}
    <section className="panel data-grid-panel">
      <div className="panel-header"><strong>Back to testing</strong><span className="muted" style={{marginLeft:8}}>({tickets.length} ticket{tickets.length === 1 ? '' : 's'})</span></div>
      <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Ticket ID</th><th>Table</th><th>Container</th><th>Date Created</th><th>Action</th></tr></thead><tbody>
        {loading && <tr><td colSpan={5} className="empty-table">Loading tickets…</td></tr>}
        {!loading && tickets.length === 0 && <tr><td colSpan={5} className="empty-table">No tickets are currently Back to testing.</td></tr>}
        {!loading && tickets.map(ticket => <tr key={ticket.id}>
          <td><Link className="table-link" href={`/problems/${ticket.id}`}>Ticket #{ticket.problem_number}</Link></td>
          <td>{ticket.table_name || '—'}</td><td>{ticket.container_id || '—'}</td>
          <td>{new Date(ticket.created_at).toLocaleString()}</td>
          <td><Link className="table-link" href={`/problems/${ticket.id}`}>Open ticket</Link></td>
        </tr>)}
      </tbody></table></div>
    </section>
  </div>;
}
