'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { ProblemTable } from '@/lib/problemTables';

export default function CreateProblemSampleWorkflowPage() {
  const router = useRouter();
  const [tables, setTables] = useState<ProblemTable[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;

    api('/problem-tables/')
      .then((data) => {
        if (!active) return;
        const rows: ProblemTable[] = Array.isArray(data) ? data : (data.results || []);
        setTables(rows);
        if (rows.length === 1) {
          router.replace(`/problems/new?table=${encodeURIComponent(rows[0].id)}`);
          return;
        }
        setLoading(false);
      })
      .catch((e) => {
        if (!active) return;
        setError(e instanceof Error ? e.message : 'Could not load problem sample tables.');
        setLoading(false);
      });

    return () => { active = false; };
  }, [router]);

  if (loading) {
    return <div>
      <h1 className="page-heading">Create Problem Sample</h1>
      <section className="panel panel-blue">
        <div className="panel-header">Problem Sample Table</div>
        <div className="panel-body"><div className="muted">Loading tables…</div></div>
      </section>
    </div>;
  }

  return <div>
    <h1 className="page-heading">Create Problem Sample</h1>

    {error ? <div className="error">{error}</div> : tables.length === 0 ? (
      <section className="panel panel-blue">
        <div className="panel-header">No Problem Sample Tables</div>
        <div className="panel-body stack">
          <div>No problem sample table exists yet. Create a table before adding a problem sample.</div>
          <div><Link className="button" href="/tables">Manage Tables</Link></div>
        </div>
      </section>
    ) : (
      <section className="panel panel-blue">
        <div className="panel-header">Which table is this problem sample for?</div>
        <div className="table-card-list">
          {tables.map((table) => (
            <Link
              href={`/problems/new?table=${encodeURIComponent(table.id)}`}
              className="table-card-row"
              key={table.id}
            >
              <div>
                <div className="result-title">
                  {table.name} {table.is_default && <span className="badge blue">Default</span>}
                </div>
                <div className="muted result-meta">{table.description || 'No description'}</div>
              </div>
              <div className="table-stats">
                <span>{table.row_count} rows</span>
                <span>Expiration: {table.pt_days === 0 ? 'Immediate' : `${table.pt_days} day${table.pt_days === 1 ? '' : 's'}`}</span>
              </div>
            </Link>
          ))}
        </div>
      </section>
    )}
  </div>;
}
