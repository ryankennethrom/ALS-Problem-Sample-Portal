'use client';

import Link from 'next/link';
import { Suspense, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';

type Ticket = {
  id: string;
  problem_number: number;
  table_id: string;
  table_name: string;
  current_workflow: string;
  created_at: string;
};

type ResponseData = {
  count: number;
  page: number;
  page_size: number;
  range: string;
  range_label: string;
  results: Ticket[];
};

const allowedRanges = new Set(['day', 'week', 'month', 'six_months', 'year', 'custom']);

function OpenedTicketsContent() {
  const searchParams = useSearchParams();
  const selectedRange = allowedRanges.has(searchParams.get('range') || '') ? (searchParams.get('range') as string) : 'week';
  const startDate = searchParams.get('start_date') || '';
  const endDate = searchParams.get('end_date') || '';
  const initialPage = Math.max(1, Number(searchParams.get('page') || '1') || 1);
  const [page, setPage] = useState(initialPage);
  const [data, setData] = useState<ResponseData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const queryBase = useMemo(() => {
    const params = new URLSearchParams({ range: selectedRange });
    if (selectedRange === 'custom') {
      if (startDate) params.set('start_date', startDate);
      if (endDate) params.set('end_date', endDate);
    }
    return params;
  }, [selectedRange, startDate, endDate]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    const params = new URLSearchParams(queryBase);
    params.set('page', String(page));
    api(`/dashboard/opened-tickets/?${params.toString()}`)
      .then((result: ResponseData) => { if (!cancelled) setData(result); })
      .catch(errorValue => { if (!cancelled) setError(errorValue instanceof Error ? errorValue.message : 'Could not load samples.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [queryBase, page]);

  const totalPages = data ? Math.max(1, Math.ceil(data.count / data.page_size)) : 1;

  return <div>
    <div className="page-toolbar">
      <div>
        <div className="eyebrow">Dashboard Analytics</div>
        <h1 className="page-heading" style={{marginBottom: 2}}>Tickets opened</h1>
        <div className="muted table-description">{data?.range_label || 'Loading selected date range…'} · across all ticket tables</div>
      </div>
      <div className="toolbar-actions"><Link href="/dashboard" className="button secondary">Back to Dashboard</Link></div>
    </div>

    {error && <div className="card error" style={{marginTop: 14}}>{error}</div>}

    <section className="panel data-grid-panel" style={{marginTop: 14}}>
      <div className="panel-header">
        <strong>Samples</strong>
        <span className="muted" style={{marginLeft: 8}}>({data?.count ?? 0} ticket{data?.count === 1 ? '' : 's'})</span>
        {loading && <span className="muted" style={{marginLeft: 'auto'}}>Loading…</span>}
      </div>
      <div className="data-table-wrap">
        <table className="data-table">
          <thead><tr><th className="row-action-column" aria-label="Open ticket"></th><th>Ticket ID</th><th>Table</th><th>Date Created</th><th>Current Workflow</th></tr></thead>
          <tbody>
            {!loading && !error && data?.results.length === 0 && <tr><td colSpan={5} className="empty-table">No tickets were opened in this range.</td></tr>}
            {data?.results.map(ticket => <tr key={ticket.id}>
              <td className="row-action-column"><Link className="row-open-link" href={`/problems/${ticket.id}`} title="Open ticket">›</Link></td>
              <td><Link className="table-link" href={`/problems/${ticket.id}`}>#{ticket.problem_number}</Link></td>
              <td>{ticket.table_name}</td>
              <td>{ticket.created_at ? new Date(ticket.created_at).toLocaleString() : '—'}</td>
              <td>{ticket.current_workflow || '—'}</td>
            </tr>)}
          </tbody>
        </table>
      </div>
      {data && totalPages > 1 && <div className="panel-body" style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap'}}>
        <button className="button secondary" type="button" disabled={page <= 1 || loading} onClick={() => setPage(current => Math.max(1, current - 1))}>Previous</button>
        <span className="muted">Page {page} of {totalPages}</span>
        <button className="button secondary" type="button" disabled={page >= totalPages || loading} onClick={() => setPage(current => Math.min(totalPages, current + 1))}>Next</button>
      </div>}
    </section>
  </div>;
}

export default function OpenedTicketsPage() {
  return <Suspense fallback={<div className="muted">Loading samples…</div>}><OpenedTicketsContent /></Suspense>;
}
