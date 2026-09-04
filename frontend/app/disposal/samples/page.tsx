'use client';

import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { changeReasonHeaders } from '@/lib/changeReason';
import { useChangeReasonModal } from '@/components/ChangeReasonModal';
import WorkflowQueueAdvancedSearch from '@/components/WorkflowQueueAdvancedSearch';
import { QueueAdvancedFilter, QueueMatchMode, matchesWorkflowQueueAdvanced } from '@/lib/workflowQueueSearch';

type DisposalSample = {
  id: string;
  problem_number: number;
  created_at: string;
  table_name?: string;
  container_id?: string;
  container_disposed?: boolean;
  workflow_status?: string;
  distributor?: string;
  end_user?: string;
  brand?: string;
  als_tracking_number?: string;
  courier_tracking_number?: string;
  custom_values?: Record<string, unknown>;
};

function textValue(value: unknown) {
  if (value == null) return '';
  if (Array.isArray(value)) return value.join(', ');
  return String(value);
}

function rowValue(item: DisposalSample, directValue: unknown, fieldKeys: string[]) {
  if (textValue(directValue).trim()) return textValue(directValue);
  for (const key of fieldKeys) {
    const value = item.custom_values?.[key];
    if (textValue(value).trim()) return textValue(value);
  }
  return '—';
}

export default function DisposeSamplesPage() {
  const { requestChangeReason, changeReasonModal } = useChangeReasonModal();
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<DisposalSample[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [selectedItems, setSelectedItems] = useState<Record<string, DisposalSample>>({});
  const [loading, setLoading] = useState(false);
  const [disposing, setDisposing] = useState(false);
  const [disposingOne, setDisposingOne] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [advancedFilters, setAdvancedFilters] = useState<QueueAdvancedFilter[]>([]);
  const [advancedMatch, setAdvancedMatch] = useState<QueueMatchMode>('all');
  const searchSerial = useRef(0);

  async function runSearch(search: string, hasAdvanced = advancedFilters.length > 0) {
    const trimmed = search.trim();
    if (!trimmed && !hasAdvanced) {
      setItems([]);
      setLoading(false);
      setError('');
      return;
    }
    const serial = ++searchSerial.current;
    setLoading(true);
    setError('');
    try {
      const url = trimmed
        ? `/problem-samples/disposal-search/?q=${encodeURIComponent(trimmed)}`
        : '/problem-samples/disposal-browse/';
      const data = await api(url);
      if (serial !== searchSerial.current) return;
      setItems(Array.isArray(data) ? data : (data.results || []));
    } catch (error) {
      if (serial !== searchSerial.current) return;
      setItems([]);
      setError(error instanceof Error ? error.message : 'Could not search problem samples.');
    } finally {
      if (serial === searchSerial.current) setLoading(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => runSearch(query, advancedFilters.length > 0), 250);
    return () => window.clearTimeout(timer);
  }, [query, advancedFilters.length]);

  const filteredItems = useMemo(
    () => items.filter(item => matchesWorkflowQueueAdvanced(item, advancedFilters, advancedMatch)),
    [items, advancedFilters, advancedMatch],
  );

  const selectableItems = useMemo(
    () => filteredItems.filter(item => item.workflow_status !== 'Disposed' && !item.container_disposed),
    [filteredItems],
  );

  const visibleItems = useMemo(() => {
    const currentIds = new Set(filteredItems.map(item => item.id));
    const pinnedSelected = Array.from(selected)
      .filter(id => !currentIds.has(id))
      .map(id => selectedItems[id])
      .filter((item): item is DisposalSample => Boolean(item));
    return [...pinnedSelected, ...filteredItems];
  }, [filteredItems, selected, selectedItems]);
  const selectedCount = selected.size;
  const allVisibleSelected = selectableItems.length > 0 && selectableItems.every(item => selected.has(item.id));

  function toggleOne(id: string) {
    const isSelected = selected.has(id);
    const item = items.find(candidate => candidate.id === id) || selectedItems[id];

    setSelected(previous => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

    setSelectedItems(previous => {
      const next = {...previous};
      if (isSelected) delete next[id];
      else if (item) next[id] = item;
      return next;
    });
  }

  function toggleAllVisible() {
    setSelected(previous => {
      const next = new Set(previous);
      if (allVisibleSelected) selectableItems.forEach(item => next.delete(item.id));
      else selectableItems.forEach(item => next.add(item.id));
      return next;
    });

    setSelectedItems(previous => {
      const next = {...previous};
      if (allVisibleSelected) selectableItems.forEach(item => delete next[item.id]);
      else selectableItems.forEach(item => { next[item.id] = item; });
      return next;
    });
  }

  async function disposeIds(ids: string[], oneId?: string) {
    if (!ids.length) return;
    const noun = ids.length === 1 ? 'problem sample' : 'problem samples';
    const reason = await requestChangeReason(`Why are you disposing ${ids.length} ${noun}?`);
    if (reason === null) return;
    if (!confirm(`Mark ${ids.length} ${noun} as Disposed? This should only be done after the sample${ids.length === 1 ? ' has' : 's have'} actually been disposed.`)) return;

    if (oneId) setDisposingOne(oneId);
    else setDisposing(true);
    setError('');
    try {
      await api('/problem-samples/bulk-dispose/', {
        method: 'POST',
        headers: changeReasonHeaders(reason),
        body: JSON.stringify({ problem_ids: ids }),
        successMessage: `${ids.length} ${noun} marked Disposed.`,
        errorMessage: 'Could not dispose the selected problem samples',
      });
      setSelected(previous => {
        const next = new Set(previous);
        ids.forEach(id => next.delete(id));
        return next;
      });
      setSelectedItems(previous => {
        const next = {...previous};
        ids.forEach(id => delete next[id]);
        return next;
      });
      await runSearch(query, advancedFilters.length > 0);
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Could not dispose the selected problem samples.');
    } finally {
      if (oneId) setDisposingOne(null);
      else setDisposing(false);
    }
  }

  return <div>
    <div className="page-toolbar">
      <div>
        <div className="eyebrow">Disposal</div>
        <h1 className="page-heading" style={{marginBottom: 2}}>Dispose Samples</h1>
        <div className="muted table-description">Quickly search for problem samples and mark one or several as Disposed. Individually disposed samples are ignored by later container-disposal readiness checks.</div>
      </div>
      <div className="toolbar-actions">
        <button className="button danger" type="button" onClick={() => disposeIds(Array.from(selected))} disabled={!selectedCount || disposing || disposingOne !== null}>
          {disposing ? 'Disposing…' : selectedCount ? `Dispose Selected (${selectedCount})` : 'Dispose Selected'}
        </button>
      </div>
    </div>

    {error && <div className="card error" style={{marginBottom: 14}}>{error}</div>}

    <section className="panel panel-blue shipping-panel">
      <div className="shipping-toolbar">
        <div className="search-grid table-search-grid compact-table-search-grid advanced-search-grid" style={{flex: 1}}>
          <div className="field search-wide">
            <label htmlFor="disposal-sample-search">Search problem samples</label>
            <input
              id="disposal-sample-search"
              className="input"
              autoFocus
              value={query}
              onChange={event => setQuery(event.target.value)}
              placeholder="Problem #6, container, client, tracking number, any searchable field…"
            />
          </div>
          <WorkflowQueueAdvancedSearch
            activeCount={advancedFilters.length}
            onApply={(filters, match) => { setAdvancedFilters(filters); setAdvancedMatch(match); }}
            onClear={() => { setAdvancedFilters([]); setAdvancedMatch('all'); }}
          />
        </div>
        <div className="shipping-summary">
          {query.trim() || advancedFilters.length ? <><strong>{filteredItems.length}</strong> match{filteredItems.length === 1 ? '' : 'es'}</> : 'Start typing or use Advanced Search'}
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
                <input type="checkbox" aria-label="Select all disposable search results" checked={allVisibleSelected} onChange={toggleAllVisible} disabled={selectableItems.length === 0 || disposing || disposingOne !== null} />
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
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {!query.trim() && advancedFilters.length === 0 && selectedCount === 0 && <tr><td colSpan={11} className="empty-table">Search for a problem sample to dispose or use Advanced Search.</td></tr>}
            {(query.trim() || advancedFilters.length > 0) && loading && <tr><td colSpan={11} className="empty-table">Searching…</td></tr>}
            {(query.trim() || advancedFilters.length > 0) && !loading && filteredItems.length === 0 && selectedCount === 0 && <tr><td colSpan={11} className="empty-table">No problem samples match your search.</td></tr>}
            {!loading && visibleItems.map(item => {
              const alreadyDisposed = item.workflow_status === 'Disposed';
              const blockedByContainer = Boolean(item.container_disposed) && !alreadyDisposed;
              const disabled = alreadyDisposed || blockedByContainer || disposing || disposingOne !== null;
              return <tr key={item.id} className={selected.has(item.id) ? 'shipping-row-selected' : ''}>
                <td className="shipping-select-column">
                  <input type="checkbox" aria-label={`Select problem ${item.problem_number}`} checked={selected.has(item.id)} onChange={() => toggleOne(item.id)} disabled={disabled} />
                </td>
                <td>
                  <Link className="table-link" href={`/problems/${item.id}`}>Problem #{item.problem_number}</Link>
                  {selected.has(item.id) && !filteredItems.some(result => result.id === item.id) && <div className="muted result-meta">Selected — kept visible</div>}
                </td>
                <td>{item.created_at ? new Date(item.created_at).toLocaleString() : '—'}</td>
                <td>{item.table_name || '—'}</td>
                <td>{item.container_id || '—'}{blockedByContainer && <div className="muted result-meta">Container already disposed</div>}</td>
                <td>{rowValue(item, item.distributor, ['distributor'])}</td>
                <td>{rowValue(item, item.end_user, ['end-user', 'end_user'])}</td>
                <td>{rowValue(item, item.brand, ['brand'])}</td>
                <td>{rowValue(item, item.als_tracking_number, ['als-tracking-number', 'als_tracking_number'])}</td>
                <td><span className="badge">{item.workflow_status || '—'}</span></td>
                <td>
                  {alreadyDisposed
                    ? <span className="muted">Already disposed</span>
                    : blockedByContainer
                      ? <span className="muted">Undo container disposal first</span>
                      : <button type="button" className="button danger compact-button" onClick={() => disposeIds([item.id], item.id)} disabled={disabled}>{disposingOne === item.id ? 'Disposing…' : 'Dispose'}</button>}
                </td>
              </tr>;
            })}
          </tbody>
        </table>
      </div>
    </section>
    {changeReasonModal}
  </div>;
}
