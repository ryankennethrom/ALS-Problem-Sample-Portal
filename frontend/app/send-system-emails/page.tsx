'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { invokeCustomerEmail, mailtoForCustomerEmail } from '@/lib/customerEmail';
import { useCurrentUser } from '@/components/CurrentUserContext';
import styles from './systemEmails.module.css';

type SystemEmail = {
  id: string;
  type: string;
  status: 'pending' | 'sent';
  table: string;
  distributor_pattern: string;
  period_start: string;
  period_end: string;
  matched_ticket_count: number;
  recipient_count: number;
  subject: string;
  created_at: string;
  sent_at: string | null;
  to_emails?: string[];
  body?: string;
};

export default function SendSystemEmailsPage() {
  const user = useCurrentUser();
  const [emails, setEmails] = useState<SystemEmail[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [selected, setSelected] = useState<SystemEmail | null>(null);
  const [opened, setOpened] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [showAll, setShowAll] = useState(false);

  async function load(all = showAll) {
    setLoading(true);
    try {
      const response: {pending_count:number;emails:SystemEmail[]} = await api(`/system-emails/${all ? '?status=all' : ''}`);
      setEmails(response.emails);
      setPendingCount(response.pending_count);
      setError('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to load system emails.');
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { void load(showAll); }, [showAll]);

  async function preview(id: string) {
    setBusy(true); setError(''); setOpened(false); setSuccess('');
    try {
      const detail: SystemEmail = await api(`/system-emails/${id}/`);
      if (detail.status !== 'pending') throw new Error('This email has already been marked sent.');
      setSelected(detail);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to load this draft.');
    } finally { setBusy(false); }
  }

  function openMailApp() {
    if (!selected?.to_emails?.length || !selected.body || opened) return;
    invokeCustomerEmail(mailtoForCustomerEmail({
      to: selected.to_emails, cc: [], subject: selected.subject, body: selected.body,
    }));
    setOpened(true);
  }

  async function confirmSent() {
    if (!selected || !opened) return;
    setBusy(true); setError('');
    try {
      await api(`/system-emails/${selected.id}/confirm-sent/`, {
        method: 'POST', body: JSON.stringify({confirmation: 'sent'}),
      });
      setSelected(null); setOpened(false);
      setSuccess('Email marked as sent. Its delivery is confirmed by staff, not verified by the mail app.');
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not confirm sending.');
    } finally { setBusy(false); }
  }

  async function queueDue() {
    setBusy(true); setError(''); setSuccess('');
    try {
      const result: {created:number;period_start:string} = await api('/system-emails/queue-due/', {method:'POST'});
      setSuccess(`${result.created} new monthly report(s) queued for ${result.period_start.slice(0,7)}. Existing reports were not duplicated.`);
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not queue monthly reports.'); }
    finally { setBusy(false); }
  }

  return <main className={styles.page}>
    <div className={styles.titleRow}>
      <div><h1 className="page-heading">Send System Emails</h1>
        <p className={styles.help}>Review monthly Distributor reports before sending them with Outlook webmail. No system email is sent automatically.</p>
      </div>
      <div className={styles.actions}>
        <button type="button" className="button secondary" disabled={busy || loading} onClick={() => void load()}>Refresh</button>
        {user?.is_admin && <button type="button" className="button secondary" disabled={busy} onClick={queueDue}>Check for due reports</button>}
      </div>
    </div>

    <section id="pending-system-emails" aria-labelledby="pending-system-emails-heading">
      <div className={styles.titleRow}>
        <h2 id="pending-system-emails-heading" className={styles.sectionTitle}>Pending System Emails ({pendingCount})</h2>
        <label className={styles.toggle}><input type="checkbox" checked={showAll} onChange={event => setShowAll(event.target.checked)} /> Show sent history</label>
      </div>
      {error && <p role="alert" className={styles.error}>{error}</p>}
      {success && <p role="status" className={styles.success}>{success}</p>}
      {loading && <p className={styles.help}>Loading emails…</p>}
      {!loading && !emails.length && <p className={styles.empty}>There are no {showAll ? '' : 'pending '}system emails. Reports appear after the monthly scheduler queues them.</p>}
      <div className={styles.list}>
        {emails.map(mail => <article key={mail.id} className={styles.mailCard}>
          <div className={styles.mailDetails}>
            <strong>{mail.subject}</strong>
            <div className={styles.meta}>{mail.table} · Distributor pattern: {mail.distributor_pattern} · {mail.period_start.slice(0,7)}</div>
            <div className={styles.meta}>{mail.matched_ticket_count} matching ticket(s) · {mail.recipient_count} recipient(s) · {mail.status === 'sent' ? 'Sent' : 'Pending'}</div>
          </div>
          {mail.status === 'pending' && <button type="button" className="button" disabled={busy} onClick={() => void preview(mail.id)}>Review and send</button>}
        </article>)}
      </div>
    </section>

    {selected && <div className={styles.overlay} role="presentation" onMouseDown={event => {if (event.target === event.currentTarget) {setSelected(null);setOpened(false);}}}>
      <section className={styles.dialog} role="dialog" aria-modal="true" aria-labelledby="system-email-dialog-title">
        <div className={styles.titleRow}>
          <h2 id="system-email-dialog-title">Review Distributor monthly report</h2>
          <button type="button" className="button secondary" onClick={() => {setSelected(null);setOpened(false);}}>Close</button>
        </div>
        <p className={styles.help}>Opening an email draft does not send it. Only confirm below after actually sending it in Outlook webmail.</p>
        <div className={styles.field}><label htmlFor="system-email-to">To</label><input id="system-email-to" className="input" readOnly value={selected.to_emails?.join(', ') || ''}/></div>
        <div className={styles.field}><label htmlFor="system-email-subject">Subject</label><input id="system-email-subject" className="input" readOnly value={selected.subject}/></div>
        <div className={styles.field}><label htmlFor="system-email-body">Message</label><textarea id="system-email-body" rows={14} className="textarea" readOnly value={selected.body || ''}/></div>
        {opened && <p className={styles.success} role="status">Draft opened in Outlook webmail. Did you actually send it?</p>}
        <div className={styles.actions}>
          {!opened ? <button type="button" className="button" onClick={openMailApp}>Open Outlook webmail to send</button> : <>
            <button type="button" className="button" disabled={busy} onClick={confirmSent}>{busy ? 'Saving…' : 'I sent the email'}</button>
            <button type="button" className="button secondary" disabled={busy} onClick={() => setOpened(false)}>I didn’t send it</button>
          </>}
          <button type="button" className="button secondary" onClick={() => {setSelected(null);setOpened(false);}}>Cancel</button>
        </div>
      </section>
    </div>}
  </main>;
}
