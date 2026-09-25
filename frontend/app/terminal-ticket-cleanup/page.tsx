'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';

type Preview = {
  start_date: string;
  end_date: string;
  count: number;
  by_workflow: Record<string, number>;
  fingerprint: string;
};
type Definition = { age_months: number; default_end_date: string };

const endpoint = '/admin/terminal-ticket-cleanup/';
const definitionEndpoint = '/admin/old-ticket-definition/';
const number = (value: number) => new Intl.NumberFormat('en-CA').format(value);

export default function TerminalTicketCleanupPage() {
  const router = useRouter();
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [savedAgeMonths, setSavedAgeMonths] = useState<number | null>(null);
  const [ageDraft, setAgeDraft] = useState('24');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [confirmation, setConfirmation] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const me: { is_admin: boolean } = await api('/auth/me/');
        if (!me.is_admin) { router.replace('/'); return; }
        const [definition, result]: [Definition, Preview] = await Promise.all([
          api(definitionEndpoint), api(endpoint),
        ]);
        if (active) {
          setSavedAgeMonths(definition.age_months);
          setAgeDraft(String(definition.age_months));
          setStartDate(result.start_date);
          setEndDate(result.end_date);
          setPreview(result);
        }
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : 'Could not preview tickets.');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, [router]);

  function changeStart(value: string) {
    setStartDate(value); setPreview(null); setConfirmation(''); setMessage(''); setError('');
  }

  function changeEnd(value: string) {
    setEndDate(value); setPreview(null); setConfirmation(''); setMessage(''); setError('');
  }

  async function loadPreview(event?: FormEvent) {
    event?.preventDefault();
    setBusy(true); setError(''); setMessage(''); setConfirmation(''); setPreview(null);
    try {
      const params = new URLSearchParams({ end_date: endDate });
      if (startDate) params.set('start_date', startDate);
      const result: Preview = await api(`${endpoint}?${params}`);
      setPreview(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not preview tickets.');
    } finally { setBusy(false); }
  }

  async function saveDefinition(event: FormEvent) {
    event.preventDefault();
    const months = Number(ageDraft);
    if (!Number.isInteger(months) || months < 1 || months > 1200) {
      setError('Enter a whole number of months from 1 to 1200.');
      return;
    }
    setBusy(true); setError(''); setMessage(''); setConfirmation(''); setPreview(null);
    try {
      const saved: Definition = await api(definitionEndpoint, {
        method: 'PUT', body: JSON.stringify({ age_months: months }),
      });
      setSavedAgeMonths(saved.age_months);
      setAgeDraft(String(saved.age_months));
      setStartDate('');
      setEndDate(saved.default_end_date);
      const result: Preview = await api(endpoint);
      setPreview(result);
      setMessage(`Old Tickets now means tickets at least ${saved.age_months} month${saved.age_months === 1 ? '' : 's'} old. The default deletion preview has been updated.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not update the Old Tickets definition.');
    } finally { setBusy(false); }
  }

  async function deleteTickets() {
    if (!preview || !preview.count || busy || confirmation !== `DELETE ${preview.count}`) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const result: { deleted_tickets: number } = await api(endpoint, {
        method: 'POST',
        body: JSON.stringify({
          start_date: preview.start_date,
          end_date: preview.end_date,
          expected_count: preview.count,
          fingerprint: preview.fingerprint,
          confirmation,
        }),
      });
      setMessage(`${number(result.deleted_tickets)} ticket${result.deleted_tickets === 1 ? '' : 's'} deleted.`);
      setConfirmation('');
      setPreview(null);
    } catch (e) {
      setPreview(null);
      setConfirmation('');
      setError(e instanceof Error ? e.message : 'Deletion failed. Preview again.');
    } finally { setBusy(false); }
  }

  return <div>
    <div className="page-heading-row"><div>
      <div className="eyebrow">Admin</div>
      <h1 className="page-heading">Delete Old Tickets</h1>
      <p className="muted">Delete tickets whose Current Workflow is <strong>Disposed</strong> or <strong>Shipped back to client</strong> and whose creation date falls in the selected range.</p>
    </div></div>

    <section className="panel" style={{maxWidth: 720, marginBottom: 18}}>
      <div className="panel-header">Define Old Tickets</div>
      <form className="panel-body" onSubmit={saveDefinition}>
        <p className="muted">A ticket becomes old after this many calendar months. This setting controls the Old Tickets dashboard count across all tables and the default date range below.</p>
        <div className="field" style={{maxWidth: 240, marginBottom: 16}}>
          <label htmlFor="old-ticket-age">Age in months</label>
          <input id="old-ticket-age" className="input" type="number" min="1" max="1200" step="1" required value={ageDraft} onChange={e => setAgeDraft(e.target.value)} disabled={loading || busy} />
        </div>
        <button className="button secondary" type="submit" disabled={loading || busy || String(savedAgeMonths) === ageDraft}>{busy ? 'Working…' : 'Save age definition'}</button>
        {savedAgeMonths != null && <p className="muted" style={{marginTop: 12}}>Current definition: {savedAgeMonths} month{savedAgeMonths === 1 ? '' : 's'}.</p>}
      </form>
    </section>

    <section className="panel" style={{maxWidth: 720}}>
      <div className="panel-header">Creation date range</div>
      <form className="panel-body" onSubmit={loadPreview}>
        <p className="muted">The default includes finished tickets older than the configured {savedAgeMonths ?? 24} month threshold. Leave the start date empty to include all older tickets. The end date is inclusive in the Edmonton timezone.</p>
        <div className="search-grid table-search-grid" style={{marginBottom: 16}}>
          <div className="field"><label htmlFor="cleanup-start">Start date (optional)</label><input id="cleanup-start" className="input" type="date" value={startDate} onChange={e => changeStart(e.target.value)} disabled={loading || busy} /></div>
          <div className="field"><label htmlFor="cleanup-end">End date (inclusive)</label><input id="cleanup-end" className="input" type="date" required value={endDate} onChange={e => changeEnd(e.target.value)} disabled={loading || busy} /></div>
        </div>
        <button className="button secondary" type="submit" disabled={loading || busy || !endDate}>{busy ? 'Working…' : 'Preview tickets'}</button>
      </form>
    </section>

    {error && <div className="card error" role="alert" style={{marginTop: 16}}>{error}</div>}
    {message && <div className="card" role="status" style={{marginTop: 16}}>{message}</div>}

    {preview && <section className="panel" style={{maxWidth: 720, marginTop: 18}}>
      <div className="panel-header">Deletion preview</div>
      <div className="panel-body">
        <p><strong>{number(preview.count)} ticket{preview.count === 1 ? '' : 's'}</strong> created {preview.start_date ? `from ${preview.start_date} through` : 'on or before'} {preview.end_date}.</p>
        <p className="muted">Disposed: {number(preview.by_workflow['Disposed'] || 0)} · Shipped back to client: {number(preview.by_workflow['Shipped back to client'] || 0)}</p>
        {preview.count > 0 && <>
          <p>Deleting these tickets also deletes their tracking links and associated ticket records and files. This cannot be undone.</p>
          <div className="field" style={{marginBottom: 14}}>
            <label htmlFor="cleanup-confirm">Type <strong>DELETE {preview.count}</strong> to confirm</label>
            <input id="cleanup-confirm" className="input" autoComplete="off" value={confirmation} onChange={e => setConfirmation(e.target.value)} disabled={busy} />
          </div>
          <button className="button" type="button" disabled={busy || confirmation !== `DELETE ${preview.count}`} onClick={deleteTickets}>{busy ? 'Deleting…' : `Delete ${number(preview.count)} tickets`}</button>
        </>}
      </div>
    </section>}
  </div>;
}
