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
  status: 'empty' | 'active' | 'partially_ready' | 'ready_to_dispose' | 'disposed' | 'restored';
  samples: ContainerSample[];
  created_by_email: string;
  created_at: string;
  disposed_at: string | null;
  disposed_by_email: string;
  is_dumping: boolean;
  source_container_id: string | null;
  dumped_sample_ids: string[];
  restored_at: string | null;
  restored_to_container_id: string | null;
};

function statusLabel(container: ProblemContainer) {
  if (container.status === 'restored') return 'RESTORED';
  if (container.is_dumping && container.status === 'disposed') return 'DUMPING — DISPOSED';
  if (container.status === 'disposed') return 'DISPOSED (LEGACY)';
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
  return !container.is_dumping && container.ready_to_dispose && container.status !== 'disposed';
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
  const [newDumpId, setNewDumpId] = useState('');
  const [query, setQuery] = useState('');
  const [cutoffDate, setCutoffDate] = useState('');
  const [disposingId, setDisposingId] = useState<number | null>(null);
  const [undoingId, setUndoingId] = useState<number | null>(null);
  const [restoreDump, setRestoreDump] = useState<ProblemContainer | null>(null);
  const [restoreMode, setRestoreMode] = useState<'existing' | 'new'>('existing');
  const [restoreTargetId, setRestoreTargetId] = useState('');

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
    if (!confirm(`Transfer the contents of ${container.container_id} into a new dumping container and mark tickets Disposed? The original container will be empty and reusable. Make sure the physical contents are transferred too.`)) return;
    const reason = await requestChangeReason(`Why are you disposing ${container.container_id}?`);
    if (reason === null) return;
    setDisposingId(container.id); setError('');
    try {
      const dumped = await api(`/problem-containers/${container.id}/dispose/`, {method:'POST', headers:changeReasonHeaders(reason), body:JSON.stringify({}), successMessage:`${container.container_id} transferred successfully.`, errorMessage:'Could not dispose container'});
      setNewDumpId(String(dumped.container_id || ''));
      await load();
    } catch(e) { setError(e instanceof Error ? e.message : 'Could not dispose container'); }
    finally { setDisposingId(null); }
  }

  async function disposeContainerByDate(container: ProblemContainer) {
    if (!cutoffDate) return;
    if (!confirm(`Transfer the contents of ${container.container_id} into a new dumping container? Every ticket was created before ${cutoffDate}. The original container will be empty and reusable. Make sure the physical contents are transferred too.`)) return;
    const reason = await requestChangeReason(`Why are you disposing ${container.container_id} using the ${cutoffDate} cutoff date?`);
    if (reason === null) return;
    setDisposingId(container.id); setError('');
    try {
      const dumped = await api(`/problem-containers/${container.id}/dispose-by-date/`, {
        method:'POST',
        headers:changeReasonHeaders(reason),
        body:JSON.stringify({ cutoff_date: cutoffDate }),
        successMessage:`${container.container_id} transferred successfully.`,
        errorMessage:'Could not dispose container by date',
      });
      setNewDumpId(String(dumped.container_id || ''));
      await load();
    } catch(e) { setError(e instanceof Error ? e.message : 'Could not dispose container by date'); }
    finally { setDisposingId(null); }
  }

  function undoContainerDisposal(container: ProblemContainer) {
    if (container.is_dumping) {
      setRestoreDump(container);
      setRestoreMode('existing');
      setRestoreTargetId('');
      return;
    }
    // Backward compatibility for disposed physical containers created before
    // the dumping-container workflow was introduced.
    void submitUndoDisposal(container, {});
  }

  async function submitUndoDisposal(container: ProblemContainer, destination: {destination_container_id?: string; create_new_container?: boolean}) {
    if (!container.is_dumping && !confirm(container.sample_count === 0
      ? `Make ${container.container_id} available for tickets again? This will clear its legacy disposed status while retaining the disposal record for audit. Confirm the physical container is safe to reuse.`
      : `Undo legacy disposal of ${container.container_id}?`)) return;
    setRestoreDump(null);
    const reason = await requestChangeReason(container.is_dumping || container.sample_count > 0
      ? `Why are you undoing disposal of ${container.container_id}?`
      : `Why are you making ${container.container_id} available again?`);
    if (reason === null) return;
    setUndoingId(container.id); setError('');
    try {
      const result = await api(`/problem-containers/${container.id}/undo-disposal/`, {
        method: 'POST', headers: changeReasonHeaders(reason), body: JSON.stringify(destination),
        successMessage: container.is_dumping ? `${container.container_id} contents restored successfully.` : container.sample_count === 0 ? `${container.container_id} is available again.` : `${container.container_id} disposal undone successfully.`,
        errorMessage: 'Could not update container availability',
      });
      if (destination.create_new_container && result.restored_to_container_id) setCreatedId(result.restored_to_container_id);
      await load();
    } catch(e) { setError(e instanceof Error ? e.message : 'Could not undo container disposal'); }
    finally { setUndoingId(null); }
  }

  const readyCount = containers.filter(isReadyToDispose).length;
  const dumpedCount = containers.filter(container => container.is_dumping).length;
  const availableDestinations = containers.filter(container => !container.is_dumping && container.status !== 'disposed');
  const dateEligibleContainers = useMemo(() => {
    if (!cutoffDate) return [];
    return containers
      .filter(container => !container.is_dumping && container.status !== 'disposed' && container.samples.length > 0)
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
            .filter(container => container.is_dumping)
            .sort((a, b) => {
              const aTime = a.disposed_at ? new Date(a.disposed_at).getTime() : 0;
              const bTime = b.disposed_at ? new Date(b.disposed_at).getTime() : 0;
              return bTime - aTime;
            })
        : containers.filter(container => !container.is_dumping);
    if (!q) return visible;
    return visible.filter(container => container.container_id.toLowerCase().includes(q) || Boolean(container.source_container_id?.toLowerCase().includes(q)));
  }, [containers, query, readyOnly, byDate, recentlyDisposed, dateEligibleContainers]);

  return <div>
    <div className="page-toolbar">
      <div><div className="eyebrow">Disposal</div><h1 className="page-heading" style={{marginBottom:2}}>{readyOnly ? 'Ready to Dispose' : byDate ? 'Dispose by Date' : recentlyDisposed ? 'Dumping Containers' : 'Dispose Containers'}</h1><div className="muted table-description">{readyOnly ? 'Only containers with attached tickets all marked To be Disposed or Disposed appear here. Empty containers are not ready.' : byDate ? 'Choose a cutoff date. A non-empty container is eligible only when every ticket in it was created before that date. Tickets created on the cutoff date are not considered older than it.' : recentlyDisposed ? 'Dumping containers use their own DC IDs, separate from the PC IDs used by problem sample containers. They are listed newest first, including previously restored dumps. To undo a disposal, choose an existing physical container or create a new one.' : 'Problem sample containers use PC IDs; dumping containers use DC IDs with separate numbering. New PC containers take the lowest unused PC number; existing PC IDs are not reassigned. A previously disposed, empty PC can be made available again. A physical container is ready only when every attached ticket has Current Workflow = To be Disposed or Disposed. Disposal transfers tickets to a new dumping container and frees this original container. Empty containers are not ready. Shipping back or moving a ticket Back to testing removes it from its container; pending shipping or testing tickets still attached block disposal.'}</div></div>
      {mode === 'all' && <div className="toolbar-actions"><button className="button" type="button" onClick={createContainer} disabled={creating}>{creating ? 'Creating…' : '+ Create Container'}</button></div>}
    </div>

    <nav className="container-view-tabs" aria-label="Container views">
      <Link href="/disposal/containers" className={`container-view-tab ${readyOnly ? 'active' : ''}`}>Ready to Dispose <span className="container-view-count">{readyCount}</span></Link>
      <Link href="/disposal/containers/dispose-by-date" className={`container-view-tab ${byDate ? 'active' : ''}`}>Dispose by Date{cutoffDate && <span className="container-view-count">{dateEligibleContainers.length}</span>}</Link>
      <Link href="/disposal/containers/recently-disposed" className={`container-view-tab ${recentlyDisposed ? 'active' : ''}`}>Dumping Containers <span className="container-view-count">{dumpedCount}</span></Link>
      <Link href="/disposal/containers/all" className={`container-view-tab ${mode === 'all' ? 'active' : ''}`}>Problem Sample Containers</Link>
    </nav>

    {newDumpId && <div className="container-created-banner"><div><strong>New Dumping Container</strong><div className="container-created-id">{newDumpId}</div></div><div className="muted">Contents were transferred from the original container in the tracker. <Link className="table-link" href={`/disposal/containers/recently-disposed#container-${newDumpId}`}>View dumping container</Link>. Confirm that the physical contents were moved too.</div></div>}
    {createdId && <div className="container-created-banner"><div><strong>Container ID</strong><div className="container-created-id">{createdId}</div></div><div className="muted">Label this physical container with its ID before using it.</div></div>}
    {error && <div className="card error" style={{marginBottom:14}}>{error}</div>}

    <div className="container-summary-grid">
      <div className="panel container-summary-card"><div className="container-summary-number">{containers.filter(container => !container.is_dumping).length}</div><div className="muted">Physical containers</div></div>
      <div className={`panel container-summary-card ${(byDate ? dateEligibleContainers.length : readyCount) ? 'container-ready-summary' : ''}`}><div className="container-summary-number">{byDate ? (cutoffDate ? dateEligibleContainers.length : '—') : readyCount}</div><div className="muted">{byDate ? 'Eligible by selected date' : 'Ready to dispose'}</div></div>
    </div>

    <section className="panel panel-blue" style={{marginTop:14}}>
      <div className="panel-header"><strong>{readyOnly ? 'Ready Containers' : byDate ? 'Containers Eligible by Date' : recentlyDisposed ? 'Dumping Containers (DC)' : 'Problem Sample Containers (PC)'}</strong>{loading && <span className="muted" style={{marginLeft:'auto'}}>Loading…</span>}</div>
      <div className="panel-body stack">
        {byDate && <div className="field" style={{maxWidth:320}}><label htmlFor="dispose-cutoff-date">Dispose tickets created before</label><input id="dispose-cutoff-date" className="input" type="date" value={cutoffDate} onChange={e=>setCutoffDate(e.target.value)} /><div className="muted result-meta">All tickets in a container must have a Created date earlier than this date.</div></div>}
        <div className="field" style={{maxWidth:420}}><label htmlFor="container-search">Find Container ID</label><input id="container-search" className="input" value={query} onChange={e=>setQuery(e.target.value)} placeholder={recentlyDisposed ? "e.g. EDM DC-00001" : "e.g. EDM PC-00001"} /></div>
        {!loading && filtered.length === 0 && <div className="muted">{readyOnly ? 'No containers are ready to dispose.' : byDate ? (cutoffDate ? 'No containers have all tickets older than the selected date.' : 'Choose a cutoff date to find eligible containers.') : recentlyDisposed ? 'No dumping containers found.' : 'No containers found.'}</div>}
        <div className="container-list">
          {filtered.map(container => <article id={`container-${container.container_id}`} key={container.id} className={`container-card ${(isReadyToDispose(container) || byDate) ? 'container-card-ready' : ''} ${container.status === 'disposed' ? 'container-card-disposed' : ''}`}>
            <div className="container-card-heading">
              <div><div className="container-card-id">{container.container_id}{container.is_dumping && <span className="muted" style={{fontSize:13,marginLeft:8}}>DUMPING CONTAINER</span>}</div><div className="muted result-meta">Created {new Date(container.created_at).toLocaleString()}{container.created_by_email ? ` by ${container.created_by_email}` : ''}</div></div>
              <div className="container-heading-actions">{byDate && <span className="container-status-badge container-status-ready_to_dispose">ELIGIBLE BY DATE</span>}<span className={`container-status-badge container-status-${container.status}`}>{statusLabel(container)}</span>{byDate ? <button type="button" className="button danger" onClick={()=>disposeContainerByDate(container)} disabled={disposingId===container.id || undoingId===container.id}>{disposingId===container.id ? 'Disposing…' : 'Dispose Container'}</button> : isReadyToDispose(container) && <button type="button" className="button danger" onClick={()=>disposeContainer(container)} disabled={disposingId===container.id || undoingId===container.id}>{disposingId===container.id ? 'Disposing…' : 'Dispose Container'}</button>}{container.status === 'disposed' && <button type="button" className="button secondary" onClick={()=>undoContainerDisposal(container)} disabled={undoingId===container.id || disposingId===container.id}>{undoingId===container.id ? 'Updating…' : !container.is_dumping && container.sample_count === 0 ? 'Make Available' : 'Undo Disposal'}</button>}</div>
            </div>
            {container.is_dumping && <div className="muted result-meta">Original container: <strong>{container.source_container_id || 'Unknown'}</strong> · Transferred {container.dumped_sample_ids.length} ticket(s){container.restored_at && <> · Restored {new Date(container.restored_at).toLocaleString()} into <strong>{container.restored_to_container_id || 'Unknown'}</strong></>}</div>}
            {container.status === 'disposed' && <div className="muted result-meta">Disposed {container.disposed_at ? new Date(container.disposed_at).toLocaleString() : ''}{container.disposed_by_email ? ` by ${container.disposed_by_email}` : ''}</div>}
            <div className="container-counts"><span>{container.sample_count} sample{container.sample_count === 1 ? '' : 's'}</span><span>{container.expired_count} expired</span><span>{container.active_count} active</span><span>{container.unnotified_count} not notified</span></div>
            {container.samples.length > 0 && <div className="container-sample-list">
              {container.samples.map(sample => <div className="container-sample-row" key={sample.id}>
                <div><Link className="table-link" href={`/problems/${sample.id}`}>Ticket #{sample.problem_number}</Link><div className="muted result-meta">{sample.table_name || 'Unknown table'} · Created {new Date(sample.created_at).toLocaleDateString()} · Expiration {sample.pt_days == null ? '—' : sample.pt_days === 0 ? 'Immediate' : `${sample.pt_days} day${sample.pt_days === 1 ? '' : 's'}`} </div></div>
                <div className="container-sample-expiration"><div><span className={`badge ${sample.ready_for_disposal ? 'expiration-expired' : 'expiration-active'}`}>{sample.current_workflow || 'Follow Up Required'}</span></div>{sampleStatus(sample)}{sample.expires_at && <div className="muted result-meta">Expires {new Date(sample.expires_at).toLocaleString()}</div>}</div>
              </div>)}
            </div>}
            {container.samples.length === 0 && <div className="muted container-empty-copy">{container.is_dumping && container.restored_at ? 'Contents restored; this dumping container is retained for audit and cannot be reused.' : 'No tickets are assigned to this container yet.'}</div>}
          </article>)}
        </div>
      </div>
    </section>
    {restoreDump && <div className="change-reason-overlay" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) setRestoreDump(null); }}>
      <div className="change-reason-dialog" role="dialog" aria-modal="true" aria-labelledby="dump-restore-title" style={{maxWidth:540}}>
        <div className="dump-restore-header"><h2 id="dump-restore-title">Undo Disposal — {restoreDump.container_id}</h2><button type="button" className="button secondary" onClick={() => setRestoreDump(null)}>Close</button></div>
        <div className="stack">
          <p>Original: <strong>{restoreDump.source_container_id || 'Unknown'}</strong>. Restore {restoreDump.sample_count} ticket(s), including their previous workflows, into a physical destination container. Confirm that the physical material has been transferred as well.</p>
          <label className="field"><span>Destination</span>
            <select className="input" value={restoreMode} onChange={event => setRestoreMode(event.target.value as 'existing' | 'new')}>
              <option value="existing">Use an existing physical container</option>
              <option value="new">Create a new physical container</option>
            </select>
          </label>
          {restoreMode === 'existing' ? <label className="field"><span>Existing Container ID (required)</span>
            <select className="input" value={restoreTargetId} onChange={event => setRestoreTargetId(event.target.value)}>
              <option value="">Choose a container…</option>
              {availableDestinations.map(destination => <option key={destination.id} value={destination.container_id}>{destination.container_id} — {destination.sample_count} ticket(s){destination.container_id === restoreDump.source_container_id ? ' (original)' : ''}</option>)}
            </select>
          </label> : <p className="muted">A new container ID will be generated and displayed after the undo is completed.</p>}
          <div className="toolbar-actions" style={{justifyContent:'flex-end'}}>
            <button type="button" className="button secondary" onClick={() => setRestoreDump(null)}>Cancel</button>
            <button type="button" className="button" disabled={undoingId !== null || (restoreMode === 'existing' && !restoreTargetId)} onClick={() => void submitUndoDisposal(restoreDump, restoreMode === 'new' ? {create_new_container: true} : {destination_container_id: restoreTargetId})}>Restore Contents</button>
          </div>
        </div>
      </div>
    </div>}
    {changeReasonModal}
  </div>;
}
