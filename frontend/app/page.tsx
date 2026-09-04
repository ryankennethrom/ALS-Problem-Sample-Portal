'use client';

import Link from 'next/link';
import { Suspense, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { displayProblemValue, systemColumnHint, ProblemTable } from '@/lib/problemTables';
import AdvancedSearch, { AdvancedFilter, MatchMode } from '@/components/AdvancedSearch';
import ColumnInfo from '@/components/ColumnInfo';

type Problem = {
  id: string;
  problem_number: number;
  custom_values: Record<string, unknown>;
  search_score?: number;
  created_at: string;
  status?: string;
  customer_notified_at?: string | null;
  days_until_automatic_disposal?: number | null;
  tracking_url?: string;
  tracking_link_expiry?: string | null;
};

type AppliedAdvancedSearch = {
  tableId: string;
  filters: AdvancedFilter[];
  match: MatchMode;
};

type QuickFilterValues = Record<string, string>;
const EMPTY_QUICK_FILTERS: QuickFilterValues = {};

function HomeContent() {
  const searchParams = useSearchParams();
  const urlTableId = searchParams.get('table') || '';
  const [q, setQ] = useState('');
  const [items, setItems] = useState<Problem[]>([]);
  const [tables, setTables] = useState<ProblemTable[]>([]);
  const [tableId, setTableId] = useState(urlTableId);
  const [advanced, setAdvanced] = useState<AppliedAdvancedSearch | null>(null);
  const [quickFiltersByTable, setQuickFiltersByTable] = useState<Record<string, QuickFilterValues>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api('/problem-tables/').then(data => {
      const rows: ProblemTable[] = Array.isArray(data) ? data : (data.results || []);
      setTables(rows);
      const selected = urlTableId && rows.some(t => t.id === urlTableId) ? urlTableId : (rows.find(t => t.is_default) || rows[0])?.id || '';
      setTableId(selected);
    }).catch(e => setError(e instanceof Error ? e.message : 'Failed to load tables'));
  }, [urlTableId]);

  useEffect(() => {
    if (!tableId) { setItems([]); return; }
    const t = setTimeout(async () => {
      setLoading(true); setError('');
      try {
        const activeAdvanced = advanced?.tableId === tableId ? advanced : null;
        const quickValues = quickFiltersByTable[tableId] || EMPTY_QUICK_FILTERS;
        const quickFilters = Object.entries(quickValues)
          .filter(([, value]) => value !== '')
          .map(([field_key, value]) => ({ field_key, value }));
        let d;
        if (activeAdvanced?.filters.length || quickFilters.length) {
          d = await api('/problem-samples/advanced-search/', {
            method: 'POST',
            body: JSON.stringify({
              table: tableId,
              q: q.trim(),
              match: activeAdvanced?.match || 'all',
              filters: activeAdvanced?.filters || [],
              quick_filters: quickFilters,
            }),
          });
        } else {
          const suffix = `table=${encodeURIComponent(tableId)}`;
          const path = q.trim() ? `/problem-samples/search/?q=${encodeURIComponent(q)}&${suffix}` : `/problem-samples/?${suffix}`;
          d = await api(path);
        }
        setItems(Array.isArray(d) ? d : (d.results || []));
      } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load'); }
      finally { setLoading(false); }
    }, 250);
    return () => clearTimeout(t);
  }, [q, tableId, advanced, quickFiltersByTable]);

  const selectedTable = useMemo(() => tables.find(t => t.id === tableId), [tables, tableId]);
  const activeAdvancedCount = advanced?.tableId === tableId ? advanced.filters.length : 0;
  const choiceColumns = useMemo(
    () => selectedTable?.columns.filter(column => column.column_type === 'choice' && column.choices.length > 0) || [],
    [selectedTable],
  );
  const currentQuickFilters = tableId ? (quickFiltersByTable[tableId] || EMPTY_QUICK_FILTERS) : EMPTY_QUICK_FILTERS;
  const activeQuickFilterCount = Object.values(currentQuickFilters).filter(Boolean).length;

  function setQuickFilter(fieldKey: string, value: string) {
    if (!tableId) return;
    setQuickFiltersByTable(previous => ({
      ...previous,
      [tableId]: { ...(previous[tableId] || {}), [fieldKey]: value },
    }));
  }

  function clearQuickFilters() {
    if (!tableId) return;
    setQuickFiltersByTable(previous => ({ ...previous, [tableId]: {} }));
  }

  return <div>
    <div className="page-toolbar">
      <div>
        <div className="eyebrow">Problem Sample Table</div>
        <h1 className="page-heading" style={{marginBottom:2}}>{selectedTable?.name || 'Problem Samples'}</h1>
        {selectedTable?.description && <div className="muted table-description">{selectedTable.description}</div>}
      </div>
      <div className="toolbar-actions">
        {tableId && <Link className="button secondary" href={`/tables/${tableId}`}>+ Add / manage columns</Link>}
        {tableId && <Link className="button" href={`/problems/new?table=${tableId}`}>+ New Problem Sample</Link>}
      </div>
    </div>

    <section className="panel panel-blue search-panel">
      <div className="search-grid table-search-grid compact-table-search-grid advanced-search-grid">
        <div className="search-field search-wide"><label htmlFor="sample-search">Search:</label><input id="sample-search" className="input" autoFocus placeholder="Search this table…" value={q} onChange={e => setQ(e.target.value)} disabled={!selectedTable}/></div>
        {selectedTable && <AdvancedSearch
          key={selectedTable.id}
          table={selectedTable}
          activeCount={activeAdvancedCount}
          onApply={(filters, match) => setAdvanced({ tableId: selectedTable.id, filters, match })}
          onClear={() => setAdvanced(null)}
        />}
      </div>
      {activeAdvancedCount > 0 && <div className="active-filter-summary">
        <span className="badge blue">Advanced search active: {activeAdvancedCount} condition{activeAdvancedCount === 1 ? '' : 's'}</span>
        <button className="filter-clear-link" type="button" onClick={() => setAdvanced(null)}>Clear advanced search</button>
      </div>}

      {choiceColumns.length > 0 && <div className="quick-filters-section">
        <div className="quick-filters-heading-row">
          <div>
            <div className="quick-filters-title">Quick Filters</div>
            <div className="muted quick-filters-help">Filter this table using its choice fields.</div>
          </div>
          {activeQuickFilterCount > 0 && <button type="button" className="filter-clear-link" onClick={clearQuickFilters}>Clear quick filters</button>}
        </div>
        <div className="quick-filters-grid">
          {choiceColumns.map(column => {
            const filterId = `quick-filter-${column.id}`;
            return <div className="quick-filter-field" key={column.id}>
              <div className="quick-filter-label-row"><label htmlFor={filterId}>{column.name}</label><ColumnInfo text={column.description} label={column.name} /></div>
              <select id={filterId} className="select" value={currentQuickFilters[column.field_key] || ''} onChange={event => setQuickFilter(column.field_key, event.target.value)}>
                <option value="">All</option>
                {column.choices.map(choice => <option key={choice} value={choice}>{choice}</option>)}
              </select>
            </div>;
          })}
        </div>
        {activeQuickFilterCount > 0 && <div className="quick-filter-status">
          <span className="badge blue">Quick filters active: {activeQuickFilterCount}</span>
        </div>}
      </div>}
    </section>

    {error && <div className="card error" style={{marginTop:14}}>{error} — sign in if your session has expired.</div>}

    {selectedTable && <section className="panel data-grid-panel" style={{marginTop:14}}>
      <div className="panel-header"><strong>{selectedTable.name}</strong><span className="muted" style={{marginLeft:8}}>({items.length} rows)</span>{loading && <span className="muted" style={{marginLeft:'auto'}}>Searching…</span>}</div>
      <div className="data-table-wrap">
        <table className="data-table">
          <thead><tr>
            <th className="row-action-column" aria-label="Open row"></th>
            <th>Date Created<div className="column-type-hint">Built-in</div></th>
            {selectedTable.columns.map(c => <th key={c.id}><div className="table-column-heading"><span>{c.name}</span><ColumnInfo text={c.description} label={c.name} /></div><div className="column-type-hint">{c.is_system ? systemColumnHint(c) : c.column_type_label}</div></th>)}
          </tr></thead>
          <tbody>
            {!loading && items.length === 0 && <tr><td colSpan={2 + selectedTable.columns.length} className="empty-table">No problem samples found</td></tr>}
            {items.map(p => <tr key={p.id}>
              <td className="row-action-column"><Link className="row-open-link" href={`/problems/${p.id}`} title="Open row">›</Link>{p.search_score != null && <div className="score">{Math.round(p.search_score)}</div>}</td>
              <td>{p.created_at ? new Date(p.created_at).toLocaleString() : '—'}</td>
              {selectedTable.columns.map(c => <td key={c.id}>{c.field_key === 'system-tracking-link' && p.tracking_url
                ? <a className="table-link" href={p.tracking_url} target="_blank" rel="noreferrer">Open tracking link</a>
                : displayProblemValue(c, p)}</td>)}
            </tr>)}
          </tbody>
        </table>
      </div>
    </section>}
  </div>;
}

export default function Home() {
  return (
    <Suspense fallback={<div className="muted">Loading problem samples…</div>}>
      <HomeContent />
    </Suspense>
  );
}
