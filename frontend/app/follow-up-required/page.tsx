'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import AdvancedSearch, { AdvancedFilter, MatchMode } from '@/components/AdvancedSearch';
import ColumnInfo from '@/components/ColumnInfo';
import { displayProblemValue, ProblemTable, systemColumnHint } from '@/lib/problemTables';

type FollowUpSample = {
  id: string;
  problem_number: number;
  table: string;
  table_name?: string;
  container_id?: string;
  workflow_status?: string;
  custom_values?: Record<string, unknown>;
  pt_days?: number;
  days_until_automatic_disposal?: number | null;
  tracking_url?: string;
  tracking_link_expiry?: string | null;
  customer_notified_at?: string | null;
  created_at: string;
};

type AppliedAdvancedSearch = {
  tableId: string;
  filters: AdvancedFilter[];
  match: MatchMode;
};

type QuickFilterValues = Record<string, string>;
const EMPTY_QUICK_FILTERS: QuickFilterValues = {};

function formatAge(createdAt: string, nowMs: number) {
  const createdMs = new Date(createdAt).getTime();
  if (!Number.isFinite(createdMs)) return '—';

  const totalMinutes = Math.max(0, Math.floor((nowMs - createdMs) / 60000));
  const days = Math.floor(totalMinutes / 1440);
  const hours = Math.floor((totalMinutes % 1440) / 60);
  const minutes = totalMinutes % 60;

  if (days > 0) return `${days} day${days === 1 ? '' : 's'}${hours ? `, ${hours} hr` : ''}`;
  if (hours > 0) return `${hours} hr${hours === 1 ? '' : 's'}${minutes ? `, ${minutes} min` : ''}`;
  return `${minutes} min`;
}


function automaticDisposalRowClass(item: FollowUpSample) {
  if (item.workflow_status !== 'Automatically Disposed') return '';
  const days = item.days_until_automatic_disposal;
  if (days == null) return '';

  const totalDays = Math.max(0, item.pt_days ?? 30);
  if (days <= 0 || totalDays === 0) return 'followup-disposal-critical';

  const remainingRatio = Math.min(1, days / totalDays);
  if (remainingRatio <= 0.10) return 'followup-disposal-critical';
  if (remainingRatio <= 0.25) return 'followup-disposal-high';
  if (remainingRatio <= 0.50) return 'followup-disposal-medium';
  if (remainingRatio <= 0.75) return 'followup-disposal-low';
  return '';
}

function formatCreatedAt(createdAt: string) {
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export default function FollowUpRequiredPage() {
  const [tables, setTables] = useState<ProblemTable[]>([]);
  const [tableId, setTableId] = useState('');
  const [items, setItems] = useState<FollowUpSample[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [tablesLoading, setTablesLoading] = useState(true);
  const [error, setError] = useState('');
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [advanced, setAdvanced] = useState<AppliedAdvancedSearch | null>(null);
  const [quickFiltersByTable, setQuickFiltersByTable] = useState<Record<string, QuickFilterValues>>({});

  useEffect(() => {
    let active = true;
    api('/problem-tables/')
      .then(data => {
        if (!active) return;
        const rows: ProblemTable[] = Array.isArray(data) ? data : (data.results || []);
        setTables(rows);
        setTableId((rows.find(table => table.is_default) || rows[0])?.id || '');
      })
      .catch(error => {
        if (!active) return;
        setError(error instanceof Error ? error.message : 'Failed to load problem sample tables.');
      })
      .finally(() => { if (active) setTablesLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!tableId) {
      setItems([]);
      setLoading(false);
      return;
    }

    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError('');
      try {
        const activeAdvanced = advanced?.tableId === tableId ? advanced : null;
        const quickValues = quickFiltersByTable[tableId] || EMPTY_QUICK_FILTERS;
        const quickFilters = Object.entries(quickValues)
          .filter(([, value]) => value !== '')
          .map(([field_key, value]) => ({ field_key, value }));
        let data;
        if (activeAdvanced?.filters.length || quickFilters.length) {
          data = await api('/problem-samples/follow-up-required/', {
            method: 'POST',
            body: JSON.stringify({
              table: tableId,
              q: query.trim(),
              filters: activeAdvanced?.filters || [],
              match: activeAdvanced?.match || 'all',
              quick_filters: quickFilters,
            }),
          });
        } else {
          const suffix = query.trim() ? `&q=${encodeURIComponent(query.trim())}` : '';
          data = await api(`/problem-samples/follow-up-required/?table=${encodeURIComponent(tableId)}${suffix}`);
        }
        setItems(Array.isArray(data) ? data : (data.results || []));
      } catch (error) {
        setError(error instanceof Error ? error.message : 'Failed to load follow-up samples.');
      } finally {
        setLoading(false);
      }
    }, 250);

    return () => window.clearTimeout(timer);
  }, [tableId, query, advanced, quickFiltersByTable]);

  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 60000);
    return () => window.clearInterval(timer);
  }, []);

  const selectedTable = useMemo(() => tables.find(table => table.id === tableId), [tables, tableId]);
  const activeAdvancedCount = advanced?.tableId === tableId ? advanced.filters.length : 0;
  const choiceColumns = useMemo(
    () => selectedTable?.columns.filter(column => column.column_type === 'choice' && column.choices.length > 0) || [],
    [selectedTable],
  );
  const currentQuickFilters = tableId ? (quickFiltersByTable[tableId] || EMPTY_QUICK_FILTERS) : EMPTY_QUICK_FILTERS;
  const activeQuickFilterCount = Object.values(currentQuickFilters).filter(Boolean).length;
  // The oldest card follows the exact currently displayed result set,
  // including basic search, Quick Filters, and Advanced Search.
  const oldest = items[0];

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

  function changeTable(nextTableId: string) {
    setTableId(nextTableId);
    setQuery('');
    setAdvanced(null);
    setQuickFiltersByTable(previous => ({ ...previous, [nextTableId]: {} }));
    setItems([]);
  }

  return <div>
    <div className="page-toolbar">
      <div>
        <div className="eyebrow">Problem Samples</div>
        <h1 className="page-heading" style={{marginBottom: 2}}>Follow-Up Required</h1>
        <div className="muted table-description">
          Problem samples under this workflow must be put for disposal, shipping, or back to testing.
        </div>
      </div>
    </div>

    {error && <div className="card error" style={{marginBottom: 14}}>{error}</div>}

    <section className="panel panel-blue search-panel" style={{marginBottom: 18}}>
      <div className="search-grid table-search-grid advanced-search-grid followup-table-search-grid">
        <div className="field">
          <label htmlFor="follow-up-table">Problem sample table</label>
          <select
            id="follow-up-table"
            className="select"
            value={tableId}
            onChange={event => changeTable(event.target.value)}
            disabled={tablesLoading || tables.length === 0}
          >
            {tables.length === 0 && <option value="">No tables available</option>}
            {tables.map(table => <option key={table.id} value={table.id}>{table.name}</option>)}
          </select>
        </div>
        <div className="field search-wide">
          <label htmlFor="follow-up-search">Search samples</label>
          <input
            id="follow-up-search"
            className="input"
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder={selectedTable ? `Search ${selectedTable.name}…` : 'Select a table first…'}
            disabled={!selectedTable}
          />
        </div>
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
            <div className="muted quick-filters-help">Filter follow-up samples using this table's choice fields.</div>
          </div>
          {activeQuickFilterCount > 0 && <button type="button" className="filter-clear-link" onClick={clearQuickFilters}>Clear quick filters</button>}
        </div>
        <div className="quick-filters-grid">
          {choiceColumns.map(column => {
            const filterId = `follow-up-quick-filter-${column.id}`;
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

    {!loading && oldest && <section
      className="card"
      style={{
        marginBottom: 18,
        padding: '22px 26px',
        border: '2px solid var(--border)',
        textAlign: 'center',
      }}
    >
      <div className="eyebrow" style={{marginBottom: 6}}>Oldest problem sample requiring follow up</div>
      <div style={{fontSize: 'clamp(2.4rem, 6vw, 4.5rem)', fontWeight: 800, lineHeight: 1}}>
        {formatAge(oldest.created_at, nowMs)}
      </div>
      <div className="muted" style={{marginTop: 9, fontSize: '0.95rem'}}>
        Problem #{oldest.problem_number} · {selectedTable?.name || oldest.table_name || 'Problem sample table'} · Created {formatCreatedAt(oldest.created_at)}
      </div>
    </section>}

    {!tablesLoading && selectedTable && !loading && !oldest && !error && <section className="card" style={{marginBottom: 18, padding: '20px 24px', textAlign: 'center'}}>
      <div className="eyebrow" style={{marginBottom: 5}}>Oldest problem sample requiring follow up</div>
      <div style={{fontSize: '1.5rem', fontWeight: 700}}>No follow-up required</div>
    </section>}

    {selectedTable && <section className="panel data-grid-panel">
      <div className="panel-header">
        <strong>{selectedTable.name}</strong>
        <span className="muted" style={{marginLeft: 8}}>({items.length} sample{items.length === 1 ? '' : 's'} requiring follow-up)</span>
        {loading && <span className="muted" style={{marginLeft: 'auto'}}>Searching…</span>}
      </div>
      <div className="data-table-wrap">
        <table className="data-table">
          <thead><tr>
            <th className="row-action-column" aria-label="Open row"></th>
            <th>Date Created<div className="column-type-hint">Built-in</div></th>
            {selectedTable.columns.map(column => <th key={column.id}>
              <div className="table-column-heading"><span>{column.name}</span><ColumnInfo text={column.description} label={column.name} /></div>
              <div className="column-type-hint">{column.is_system ? systemColumnHint(column) : column.column_type_label}</div>
            </th>)}
          </tr></thead>
          <tbody>
            {!loading && items.length === 0 && <tr><td colSpan={2 + selectedTable.columns.length} className="empty-table">No problem samples currently require follow-up in this table.</td></tr>}
            {loading && <tr><td colSpan={2 + selectedTable.columns.length} className="empty-table">Loading samples…</td></tr>}
            {!loading && items.map(item => <tr key={item.id} className={automaticDisposalRowClass(item)}>
              <td className="row-action-column"><Link className="row-open-link" href={`/problems/${item.id}`} title="Open row">›</Link></td>
              <td>{formatCreatedAt(item.created_at) || '—'}</td>
              {selectedTable.columns.map(column => <td key={column.id}>
                {column.field_key === 'problem-id'
                  ? <Link className="table-link" href={`/problems/${item.id}`}>Problem #{item.problem_number}</Link>
                  : column.field_key === 'status'
                    ? <span className="badge">{displayProblemValue(column, item)}</span>
                    : column.field_key === 'system-tracking-link' && item.tracking_url
                      ? <a className="table-link" href={item.tracking_url} target="_blank" rel="noreferrer">Open tracking link</a>
                      : displayProblemValue(column, item)}
              </td>)}
            </tr>)}
          </tbody>
        </table>
      </div>
    </section>}

    {!tablesLoading && tables.length === 0 && !error && <section className="card" style={{padding: 20}}>
      No problem sample tables exist yet. <Link className="table-link" href="/tables">Manage Tables</Link>
    </section>}
  </div>;
}
