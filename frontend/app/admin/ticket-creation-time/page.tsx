'use client';

import { FormEvent, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { useCurrentUser } from '@/components/CurrentUserContext';

type StaffRow = {staff_id:number|null; staff_name:string; tickets:number; total_ms:number; average_ms:number};
type DayRow = {date:string; tickets:number; total_ms:number; staff:StaffRow[]};
type TimeReport = {
  start_date:string; end_date:string; today:string; timezone:string;
  summary:{tickets:number; total_ms:number; average_ms:number};
  staff:StaffRow[]; daily:DayRow[];
};

function duration(ms:number) {
  const seconds = Math.round(ms / 1000);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remaining = seconds % 60;
  return [hours ? `${hours}h` : '', (hours || minutes) ? `${minutes}m` : '', `${remaining}s`].filter(Boolean).join(' ');
}
function dayOffset(iso:string, offset:number) {
  const date = new Date(`${iso}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + offset);
  return date.toISOString().slice(0,10);
}

export default function TicketCreationTimePage() {
  const user = useCurrentUser();
  const [report,setReport] = useState<TimeReport|null>(null);
  const [start,setStart] = useState('');
  const [end,setEnd] = useState('');
  const [loading,setLoading] = useState(true);
  const [error,setError] = useState('');
  const [filterStaff,setFilterStaff] = useState('all');

  async function load(startDate?:string, endDate?:string) {
    setLoading(true); setError('');
    try {
      const query = startDate && endDate ? `?start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}` : '';
      const result:TimeReport = await api(`/admin/ticket-creation-time/${query}`);
      setReport(result); setStart(result.start_date); setEnd(result.end_date);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load ticket creation report');
    } finally { setLoading(false); }
  }
  useEffect(() => { if (user?.is_admin) void load(); }, [user?.is_admin]);

  function range(days:number) {
    const finalDay = report?.today || end;
    if (!finalDay) return;
    void load(dayOffset(finalDay, -(days - 1)), finalDay);
  }
  function applyDates(e:FormEvent) { e.preventDefault(); void load(start, end); }
  if (user && !user.is_admin) return <div className="error">Administrator access is required.</div>;
  const selectedId = filterStaff === 'all' ? undefined : filterStaff;
  const rows = report?.staff.filter(item => selectedId === undefined || String(item.staff_id) === selectedId) || [];
  const detail = report?.daily.flatMap(day => day.staff
    .filter(item => selectedId === undefined || String(item.staff_id) === selectedId)
    .map(item => ({...item, date:day.date}))) || [];
  const filteredTotal = rows.reduce((sum,row) => sum + row.total_ms, 0);
  const filteredCount = rows.reduce((sum,row) => sum + row.tickets, 0);

  return <div className="stack">
    <h1 className="page-heading">Ticket Creation Time</h1>
    <p className="muted">Elapsed time from the first Create Ticket click until staff confirms “I sent the email” or “I didn’t send the email”. Only successfully created tickets count. Time includes pauses and email composition. Dates use {report?.timezone || 'America/Edmonton'} and are grouped by completion date.</p>
    <section className="panel">
      <div className="panel-header"><strong>Report period</strong></div>
      <div className="panel-body stack">
        <div style={{display:'flex', gap:8, flexWrap:'wrap'}}>
          <button className="button secondary" type="button" onClick={() => range(7)}>Last 7 days</button>
          <button className="button secondary" type="button" onClick={() => range(30)}>Last 30 days</button>
          <button className="button secondary" type="button" onClick={() => range(90)}>Last 90 days</button>
        </div>
        <form onSubmit={applyDates} style={{display:'flex', alignItems:'end', flexWrap:'wrap', gap:12}}>
          <div className="field"><label htmlFor="ticket-timing-from">From</label><input id="ticket-timing-from" className="input" type="date" value={start} onChange={e=>setStart(e.target.value)} required /></div>
          <div className="field"><label htmlFor="ticket-timing-to">To</label><input id="ticket-timing-to" className="input" type="date" value={end} onChange={e=>setEnd(e.target.value)} required /></div>
          <button className="button" disabled={loading} type="submit">Apply dates</button>
        </form>
        <div className="field" style={{maxWidth:360}}>
          <label htmlFor="ticket-timing-staff">Staff</label>
          <select className="input" id="ticket-timing-staff" value={filterStaff} onChange={e=>setFilterStaff(e.target.value)}>
            <option value="all">All staff</option>
            {report?.staff.map(row=><option key={`${row.staff_id}-${row.staff_name}`} value={String(row.staff_id)}>{row.staff_name}</option>)}
          </select>
        </div>
        {error && <div className="error">{error}</div>}
        {loading && <p className="muted">Loading timing report…</p>}
      </div>
    </section>
    {report && <>
      <section className="panel"><div className="panel-header"><strong>Summary</strong></div><div className="panel-body">
        <div className="grid">
          <div><div className="muted">Tickets created</div><h2>{filteredCount}</h2></div>
          <div><div className="muted">Total time</div><h2>{duration(filteredTotal)}</h2></div>
          <div><div className="muted">Average per ticket</div><h2>{filteredCount ? duration(filteredTotal/filteredCount) : '—'}</h2></div>
        </div>
      </div></section>
      <section className="panel"><div className="panel-header"><strong>Totals by staff</strong></div><div className="panel-body">
        {!rows.length ? <p className="muted">No completed ticket creations for the selected period.</p> : <div className="table-wrap"><table className="data-table"><thead><tr><th>Staff</th><th>Tickets</th><th>Total time</th><th>Average per ticket</th></tr></thead><tbody>
          {rows.map(row=><tr key={`${row.staff_id}-${row.staff_name}`}><td>{row.staff_name}</td><td>{row.tickets}</td><td>{duration(row.total_ms)}</td><td>{duration(row.average_ms)}</td></tr>)}
        </tbody></table></div>}
      </div></section>
      <section className="panel"><div className="panel-header"><strong>Daily breakdown by staff</strong></div><div className="panel-body">
        {!detail.length ? <p className="muted">No recorded ticket creation time for these days.</p> : <div className="table-wrap"><table className="data-table"><thead><tr><th>Completed on</th><th>Staff</th><th>Tickets</th><th>Total time</th><th>Average per ticket</th></tr></thead><tbody>
          {detail.map(row=><tr key={`${row.date}-${row.staff_id}-${row.staff_name}`}><td>{row.date}</td><td>{row.staff_name}</td><td>{row.tickets}</td><td>{duration(row.total_ms)}</td><td>{duration(row.average_ms)}</td></tr>)}
        </tbody></table></div>}
      </div></section>
    </>}
  </div>;
}
