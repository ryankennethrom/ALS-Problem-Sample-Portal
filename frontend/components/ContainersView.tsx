'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { changeReasonHeaders } from '@/lib/changeReason';
import { useChangeReasonModal } from '@/components/ChangeReasonModal';

type ContainerSample = {
  id: string;
  problem_number: number;
  table_id: string;
  table_name: string;
  pt_days: number | null;
  customer_notified_at: string | null;
  created_at: string;
  created_date: string;
  expires_at: string | null;
  expiration_status: 'active' | 'expired';
  status: string;
  current_workflow: string;
  ready_for_disposal: boolean;
  days_until_expiration: number | null;
};

type ProblemContainer = {
  id: number;
  container_id: string;
  sample_count: number;
  expired_count: number;
  active_count: number;
  unnotified_count: number;
  all_expired: boolean;
  ready_to_dispose: boolean;
  status: 'empty' | 'active' | 'partially_ready' | 'ready_to_dispose' | 'disposed';
  samples: ContainerSample[];
  created_by_email: string;
  created_at: string;
  disposed_at: string | null;
  disposed_by_email: string;
};

function statusLabel(container: ProblemContainer) {
  if (container.status === 'disposed') return 'DISPOSED';
  if (container.status === 'ready_to_dispose') return 'READY TO DISPOSE';
  if (container.status === 'partially_ready') return 'PARTIALLY READY';
  if (container.status === 'empty') return 'EMPTY';
  return 'ACTIVE';
}

function sampleStatus(sample: ContainerSample) {
  if (sample.expiration_status === 'expired') return <span className="badge expiration-expired">Expired</span>;
  return <span className="badge expiration-active">{sample.days_until_expiration ?? '—'} day{sample.days_until_expiration === 1 ? '' : 's'} left</span>;
}

function isReadyToDispose(container: ProblemContainer) {
  return container.ready_to_dispose && container.status !== 'disposed';
}

type ContainerViewMode = 'ready' | 'by-date' | 'all' | 'recently-disposed';

export default function ContainersView({ mode = 'ready' }: { mode?: ContainerViewMode }) {
  const { requestChangeReason, changeReasonModal } = useChangeReasonModal();
  const readyOnly = mode === 'ready';
  const byDate = mode === 'by-date';
  const recentlyDisposed = mode === 'recently-disposed';
  const [containers, setContainers] = useState<ProblemContainer[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [createdId, setCreatedId] = useState('');
  const [query, setQuery] = useState('');
  const [cutoffDate, setCutoffDate] = useState('');
  const [disposingId, setDisposingId] = useState<number | null>(null);
  const [undoingId, setUndoingId] = useState<number | null>(null);

  async function load() {
    const data = await api('/problem-containers/');
    setContainers(Array.isArray(data) ? data : (data.results || []));
  }

  useEffect(() => {
    load().catch(e => setError(e instanceof Error ? e.message : 'Failed to load containers')).finally(() => setLoading(false));
  }, []);

  async function createContainer() {
    setCreating(true); setError('');
    try {
      const created = await api('/problem-containers/', { method: 'POST', body: JSON.stringify({}), errorMessage: 'Could not create container' });
      setCreatedId(String(created.container_id || ''));
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not create container');
    } finally { setCreating(false); }
  }

  async function disposeContainer(container: ProblemContainer) {
    if (!confirm(`Dispose ${container.container_id}? Tickets marked To be Disposed will change to Disposed. Tickets already Disposed will stay Disposed.`)) return;
    const reason = await requestChangeReason(`Why are you disposing ${container.container_id}?`);
    if (reason === null) return;
    setDisposingId(container.id); setError('');
    try {
      await api(`/problem-containers/${container.id}/dispose/`, {method:'POST', headers:changeReasonHeaders(reason), body:JSON.stringify({}), successMessage:`${container.container_id} disposed successfully.`, errorMessage:'Could not dispose container'});
      await load();
    } catch(e) { setError(e instanceof Error ? e.message : 'Could not dispose container'); }
    finally { setDisposingId(null); }
  }

  async function disposeContainerByDate(container: ProblemContainer) {
    if (!cutoffDate) return;
    if (!confirm(`Dispose ${container.container_id}? Every ticket in this container was created before ${cutoffDate}. Any ticket not already Disposed will change to Disposed.`)) return;
    const reason = await requestChangeReason(`Why are you disposing ${container.container_id} using the ${cutoffDate} cutoff date?`);
    if (reason === null) return;
    setDisposingId(container.id); setError('');
    try {
      await api(`/problem-containers/${container.id}/dispose-by-date/`, {
        method:'POST',
        headers:changeReasonHeaders(reason),
        body:JSON.stringify({ cutoff_date: cutoffDate }),
        successMessage:`${container.container_id} disposed successfully.`,
        errorMessage:'Could not dispose container by date',
      });
      await load();
    } catch(e) { setError(e instanceof Error ? e.message : 'Could not dispose container by date'); }
    finally { setDisposingId(null); }
  }

  async function undoContainerDisposal(container: ProblemContainer) {
    if (!confirm(`Undo disposal of ${container.container_id}? The samples will be restored to the Current Workflow values they had immediately before the container was disposed.`)) return;
    const reason = await requestChangeReason(`Why are you undoing disposal of ${container.container_id}?`);
    if (reason === null) return;
    setUndoingId(container.id); setError('');
    try {
      await api(`/problem-containers/${container.id}/undo-disposal/`, {method:'POST', headers:changeReasonHeaders(reason), body:JSON.stringify({}), successMessage:`${container.container_id} disposal undone successfully.`, errorMessage:'Could not undo container disposal'});
      await load();
    } catch(e) { setError(e instanceof Error ? e.message : 'Could not undo container disposal'); }
    finally { setUndoingId(null); }
  }

  const readyCount = containers.filter(isReadyToDispose).length;
  const disposedCount = containers.filter(container => container.status === 'disposed').length;
  const dateEligibleContainers = useMemo(() => {
    if (!cutoffDate) return [];
    return containers
      .filter(container => container.status !== 'disposed' && container.samples.length > 0)
      .filter(container => container.samples.every(sample => sample.created_date < cutoffDate))
      .sort((a, b) => {
        const newestA = a.samples.reduce((latest, sample) => sample.created_date > latest ? sample.created_date : latest, '');
        const newestB = b.samples.reduce((latest, sample) => sample.created_date > latest ? sample.created_date : latest, '');
        return newestA.localeCompare(newestB);
      });
  }, [containers, cutoffDate]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let visible = readyOnly
      ? containers.filter(isReadyToDispose)
      : byDate
        ? dateEligibleContainers
        : recentlyDisposed
        ? containers
            .filter(container => container.status === 'disposed')
            .sort((a, b) => {
              const aTime = a.disposed_at ? new Date(a.disposed_at).getTime() : 0;
              const bTime = b.disposed_at ? new Date(b.disposed_at).getTime() : 0;
              return bTime - aTime;
            })
        : containers;
    if (!q) return visible;
    return visible.filter(container => container.container_id.toLowerCase().includes(q));
  }, [containers, query, readyOnly, byDate, recentlyDisposed, dateEligibleContainers]);

  return <div>
    <div className="page-toolbar">
      <div><div className="eyebrow">Disposal</div><h1 className="page-heading" style={{marginBottom:2}}>{readyOnly ? 'Ready to Dispose' : byDate ? 'Dispose by Date' : recentlyDisposed ? 'Recently Disposed' : 'Dispose Containers'}</h1><div className="muted table-description">{readyOnly ? 'Only containers with attached tickets all marked To be Disposed or Disposed appear here. Empty containers are not ready.' : byDate ? 'Choose a cutoff date. A non-empty container is eligible only when every ticket in it was created before that date. Tickets created on the cutoff date are not considered older than it.' : recentlyDisposed ? 'Disposed containers are shown newest first. Use Undo Disposal if a container was disposed by mistake.' : 'A container is ready only when every attached ticket has Current Workflow = To be Disposed or Disposed. Empty containers are not ready. Shipping back or moving a ticket Back to testing removes it from its container; pending shipping or testing tickets still attached block disposal.'}</div></div>
      {mode === 'all' && <div className="toolbar-actions"><button className="button" type="button" onClick={createContainer} disabled={creating}>{creating ? 'Creating…' : '+ Create Container'}</button></div>}
    </div>

    <nav className="container-view-tabs" aria-label="Container views">
      <Link href="/disposal/containers" className={`container-view-tab ${readyOnly ? 'active' : ''}`}>Ready to Dispose <span className="container-view-count">{readyCount}</span></Link>
      <Link href="/disposal/containers/dispose-by-date" className={`container-view-tab ${byDate ? 'active' : ''}`}>Dispose by Date{cutoffDate && <span className="container-view-count">{dateEligibleContainers.length}</span>}</Link>
      <Link href="/disposal/containers/recently-disposed" className={`container-view-tab ${recentlyDisposed ? 'active' : ''}`}>Recently Disposed <span className="container-view-count">{disposedCount}</span></Link>
      <Link href="/disposal/containers/all" className={`container-view-tab ${mode === 'all' ? 'active' : ''}`}>All Containers</Link>
    </nav>

    {createdId && <div className="container-created-banner"><div><strong>New Container ID</strong><div className="container-created-id">{createdId}</div></div><div className="muted">Label the physical container with this ID. It can now be selected when creating a ticket.</div></div>}
    {error && <div className="card error" style={{marginBottom:14}}>{error}</div>}

    <div className="container-summary-grid">
      <div className="panel container-summary-card"><div className="container-summary-number">{containers.length}</div><div className="muted">Total containers</div></div>
      <div className={`panel container-summary-card ${(byDate ? dateEligibleContainers.length : readyCount) ? 'container-ready-summary' : ''}`}><div className="container-summary-number">{byDate ? (cutoffDate ? dateEligibleContainers.length : '—') : readyCount}</div><div className="muted">{byDate ? 'Eligible by selected date' : 'Ready to dispose'}</div></div>
    </div>

    <section className="panel panel-blue" style={{marginTop:14}}>
      <div className="panel-header"><strong>{readyOnly ? 'Ready Containers' : byDate ? 'Containers Eligible by Date' : recentlyDisposed ? 'Recently Disposed Containers' : 'Container Status'}</strong>{loading && <span className="muted" style={{marginLeft:'auto'}}>Loading…</span>}</div>
      <div className="panel-body stack">
        {byDate && <div className="field" style={{maxWidth:320}}><label htmlFor="dispose-cutoff-date">Dispose tickets created before</label><input id="dispose-cutoff-date" className="input" type="date" value={cutoffDate} onChange={e=>setCutoffDate(e.target.value)} /><div className="muted result-meta">All tickets in a container must have a Created date earlier than this date.</div></div>}
        <div className="field" style={{maxWidth:420}}><label htmlFor="container-search">Find Container ID</label><input id="container-search" className="input" value={query} onChange={e=>setQuery(e.target.value)} placeholder="e.g. PC-000123" /></div>
        {!loading && filtered.length === 0 && <div className="muted">{readyOnly ? 'No containers are ready to dispose.' : byDate ? (cutoffDate ? 'No containers have all tickets older than the selected date.' : 'Choose a cutoff date to find eligible containers.') : recentlyDisposed ? 'No disposed containers found.' : 'No containers found.'}</div>}
        <div className="container-list">
          {filtered.map(container => <article id={`container-${container.container_id}`} key={container.id} className={`container-card ${(isReadyToDispose(container) || byDate) ? 'container-card-ready' : ''} ${container.status === 'disposed' ? 'container-card-disposed' : ''}`}>
            <div className="container-card-heading">
              <div><div className="container-card-id">{container.container_id}</div><div className="muted result-meta">Created {new Date(container.created_at).toLocaleString()}{container.created_by_email ? ` by ${container.created_by_email}` : ''}</div></div>
              <div className="container-heading-actions">{byDate && <span className="container-status-badge container-status-ready_to_dispose">ELIGIBLE BY DATE</span>}<span className={`container-status-badge container-status-${container.status}`}>{statusLabel(container)}</span>{byDate ? <button type="button" className="button danger" onClick={()=>disposeContainerByDate(container)} disabled={disposingId===container.id || undoingId===container.id}>{disposingId===container.id ? 'Disposing…' : 'Dispose Container'}</button> : isReadyToDispose(container) && <button type="button" className="button danger" onClick={()=>disposeContainer(container)} disabled={disposingId===container.id || undoingId===container.id}>{disposingId===container.id ? 'Disposing…' : 'Dispose Container'}</button>}{container.status === 'disposed' && <button type="button" className="button secondary" onClick={()=>undoContainerDisposal(container)} disabled={undoingId===container.id || disposingId===container.id}>{undoingId===container.id ? 'Undoing…' : 'Undo Disposal'}</button>}</div>
            </div>
            {container.status === 'disposed' && <div className="muted result-meta">Disposed {container.disposed_at ? new Date(container.disposed_at).toLocaleString() : ''}{container.disposed_by_email ? ` by ${container.disposed_by_email}` : ''}</div>}
            <div className="container-counts"><span>{container.sample_count} sample{container.sample_count === 1 ? '' : 's'}</span><span>{container.expired_count} expired</span><span>{container.active_count} active</span><span>{container.unnotified_count} not notified</span></div>
            {container.samples.length > 0 && <div className="container-sample-list">
              {container.samples.map(sample => <div className="container-sample-row" key={sample.id}>
                <div><Link className="table-link" href={`/problems/${sample.id}`}>Ticket #{sample.problem_number}</Link><div className="muted result-meta">{sample.table_name || 'Unknown table'} · Created {new Date(sample.created_at).toLocaleDateString()} · Expiration {sample.pt_days == null ? '—' : sample.pt_days === 0 ? 'Immediate' : `${sample.pt_days} day${sample.pt_days === 1 ? '' : 's'}`} </div></div>
                <div className="container-sample-expiration"><div><span className={`badge ${sample.ready_for_disposal ? 'expiration-expired' : 'expiration-active'}`}>{sample.current_workflow || 'CS Follow-Up'}</span></div>{sampleStatus(sample)}{sample.expires_at && <div className="muted result-meta">Expires {new Date(sample.expires_at).toLocaleString()}</div>}</div>
              </div>)}
            </div>}
            {container.samples.length === 0 && <div className="muted container-empty-copy">No tickets are assigned to this container yet.</div>}
          </article>)}
        </div>
      </div>
    </section>
    {changeReasonModal}
  </div>;
}
