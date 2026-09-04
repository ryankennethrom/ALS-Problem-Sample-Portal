'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { changeReasonHeaders } from '@/lib/changeReason';
import { useChangeReasonModal } from '@/components/ChangeReasonModal';
import WorkflowQueueAdvancedSearch from '@/components/WorkflowQueueAdvancedSearch';
import { QueueAdvancedFilter, QueueMatchMode, matchesWorkflowQueueAdvanced, matchesWorkflowQueueSearch } from '@/lib/workflowQueueSearch';

type ShippingSample = {
  id: string;
  problem_number: number;
  created_at: string;
  table_name?: string;
  container_id?: string;
  distributor?: string;
  end_user?: string;
  brand?: string;
  als_tracking_number?: string;
  courier?: string;
  courier_tracking_number?: string;
  custom_values?: Record<string, unknown>;
};

function textValue(value: unknown) {
  if (value == null) return '';
  if (Array.isArray(value)) return value.join(', ');
  return String(value);
}

function rowValue(item: ShippingSample, directValue: unknown, fieldKeys: string[]) {
  if (textValue(directValue).trim()) return textValue(directValue);
  for (const key of fieldKeys) {
    const value = item.custom_values?.[key];
    if (textValue(value).trim()) return textValue(value);
  }
  return '—';
}

export default function ToBeShippedPage() {
  const { requestChangeReason, changeReasonModal } = useChangeReasonModal();
  const [items, setItems] = useState<ShippingSample[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [shipping, setShipping] = useState(false);
  const [error, setError] = useState('');
  const [advancedFilters, setAdvancedFilters] = useState<QueueAdvancedFilter[]>([]);
  const [advancedMatch, setAdvancedMatch] = useState<QueueMatchMode>('all');

  async function load() {
    const data = await api('/problem-samples/to-be-shipped/');
    setItems(Array.isArray(data) ? data : (data.results || []));
    setSelected(new Set());
  }

  useEffect(() => {
    load()
      .catch(error => setError(error instanceof Error ? error.message : 'Failed to load samples to be shipped.'))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => items.filter(item =>
    matchesWorkflowQueueSearch(item, query)
    && matchesWorkflowQueueAdvanced(item, advancedFilters, advancedMatch)
  ), [items, query, advancedFilters, advancedMatch]);

  const selectedCount = selected.size;
  const allVisibleSelected = filtered.length > 0 && filtered.every(item => selected.has(item.id));

  function toggleOne(id: string) {
    setSelected(previous => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAllVisible() {
    setSelected(previous => {
      const next = new Set(previous);
      if (allVisibleSelected) filtered.forEach(item => next.delete(item.id));
      else filtered.forEach(item => next.add(item.id));
      return next;
    });
  }

  async function shipSelected() {
    if (!selectedCount) return;
    const noun = selectedCount === 1 ? 'problem sample' : 'problem samples';
    const reason = await requestChangeReason(`Why are you making this change to ${selectedCount} selected ${noun}?`);
    if (reason === null) return;
    if (!confirm(`Mark ${selectedCount} selected ${noun} as Shipped back to client?`)) return;

    setShipping(true);
    setError('');
    try {
      await api('/problem-samples/bulk-ship-back/', {
        method: 'POST',
        headers: changeReasonHeaders(reason),
        body: JSON.stringify({ problem_ids: Array.from(selected) }),
        successMessage: `${selectedCount} ${noun} marked Shipped back to client.`,
        errorMessage: 'Could not ship the selected problem samples',
      });
      await load();
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Could not ship the selected problem samples.');
    } finally {
      setShipping(false);
    }
  }

  return <div>
    <div className="page-toolbar">
      <div>
        <div className="eyebrow">Shipping</div>
        <h1 className="page-heading" style={{marginBottom: 2}}>To be shipped</h1>
        <div className="muted table-description">Select one or more problem samples that are ready to be returned to the client, then mark them as shipped together.</div>
      </div>
      <div className="toolbar-actions">
        <button className="button" type="button" onClick={shipSelected} disabled={!selectedCount || shipping}>
          {shipping ? 'Shipping…' : selectedCount ? `Ship Selected (${selectedCount})` : 'Ship Selected'}
        </button>
      </div>
    </div>

    {error && <div className="card error" style={{marginBottom: 14}}>{error}</div>}

    <section className="panel panel-blue shipping-panel">
      <div className="shipping-toolbar">
        <div className="search-grid table-search-grid compact-table-search-grid advanced-search-grid" style={{flex: 1}}>
          <div className="field search-wide">
            <label htmlFor="shipping-search">Search samples</label>
            <input id="shipping-search" className="input" value={query} onChange={event => setQuery(event.target.value)} placeholder="Problem #6, container, client, tracking number…" />
          </div>
          <WorkflowQueueAdvancedSearch
            activeCount={advancedFilters.length}
            onApply={(filters, match) => { setAdvancedFilters(filters); setAdvancedMatch(match); }}
            onClear={() => { setAdvancedFilters([]); setAdvancedMatch('all'); }}
          />
        </div>
        <div className="shipping-summary">
          <strong>{query.trim() || advancedFilters.length ? filtered.length : items.length}</strong> sample{(query.trim() || advancedFilters.length ? filtered.length : items.length) === 1 ? '' : 's'} to be shipped
          {selectedCount > 0 && <span className="badge blue">{selectedCount} selected</span>}
        </div>
      </div>
      {advancedFilters.length > 0 && <div className="active-filter-summary" style={{marginBottom: 12}}>
        <span className="badge blue">Advanced search active: {advancedFilters.length} condition{advancedFilters.length === 1 ? '' : 's'}</span>
        <button className="filter-clear-link" type="button" onClick={() => { setAdvancedFilters([]); setAdvancedMatch('all'); }}>Clear advanced search</button>
      </div>}

      <div className="data-table-wrap shipping-table-wrap">
        <table className="data-table shipping-table">
          <thead>
            <tr>
              <th className="shipping-select-column">
                <input type="checkbox" aria-label="Select all visible samples" checked={allVisibleSelected} onChange={toggleAllVisible} disabled={filtered.length === 0 || shipping} />
              </th>
              <th>Problem ID</th>
              <th>Date Created</th>
              <th>Table</th>
              <th>Container</th>
              <th>Distributor</th>
              <th>End User</th>
              <th>Brand</th>
              <th>ALS Tracking Number</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {!loading && filtered.length === 0 && <tr><td colSpan={10} className="empty-table">{items.length ? 'No samples match your search.' : 'No problem samples are waiting to be shipped.'}</td></tr>}
            {loading && <tr><td colSpan={10} className="empty-table">Loading samples…</td></tr>}
            {!loading && filtered.map(item => <tr key={item.id} className={selected.has(item.id) ? 'shipping-row-selected' : ''}>
              <td className="shipping-select-column"><input type="checkbox" aria-label={`Select problem ${item.problem_number}`} checked={selected.has(item.id)} onChange={() => toggleOne(item.id)} disabled={shipping} /></td>
              <td><Link className="table-link" href={`/problems/${item.id}`}>Problem #{item.problem_number}</Link></td>
              <td>{item.created_at ? new Date(item.created_at).toLocaleString() : '—'}</td>
              <td>{item.table_name || '—'}</td>
              <td>{item.container_id || '—'}</td>
              <td>{rowValue(item, item.distributor, ['distributor'])}</td>
              <td>{rowValue(item, item.end_user, ['end-user', 'end_user'])}</td>
              <td>{rowValue(item, item.brand, ['brand'])}</td>
              <td>{rowValue(item, item.als_tracking_number, ['als-tracking-number', 'als_tracking_number'])}</td>
              <td><span className="badge">To be shipped back to client</span></td>
            </tr>)}
          </tbody>
        </table>
      </div>
    </section>
    {changeReasonModal}
  </div>;
}
