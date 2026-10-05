'use client';

import { ChangeEvent, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, clearToken } from '@/lib/api';
import { loginUrl } from '@/lib/authRedirect';

type Status = {
  backup_format_version: number;
  schema_hash: string;
  migration_count: number;
  media_file_count: number;
  media_total_bytes: number;
  media_root: string;
  persistent_media_volume: boolean;
  database_backup_type: string;
  database_restore_logs_out_users: boolean;
};

type BackupKind = 'database' | 'media' | 'full';

const RESTORE_CONFIRMATIONS: Record<BackupKind, string> = {
  database: 'RESTORE DATABASE',
  media: 'RESTORE MEDIA',
  full: 'RESTORE FULL BACKUP',
};

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let amount = value;
  let index = 0;
  while (amount >= 1024 && index < units.length - 1) { amount /= 1024; index += 1; }
  return `${amount >= 10 || index === 0 ? amount.toFixed(0) : amount.toFixed(1)} ${units[index]}`;
}

export default function BackupRestorePage() {
  const router = useRouter();
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<BackupKind | null>(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [files, setFiles] = useState<Record<BackupKind, File | null>>({ database: null, media: null, full: null });
  const [confirmationInputs, setConfirmationInputs] = useState<Record<BackupKind, string>>({ database: '', media: '', full: '' });
  const fileInputs = {
    database: useRef<HTMLInputElement>(null),
    media: useRef<HTMLInputElement>(null),
    full: useRef<HTMLInputElement>(null),
  };

  async function loadStatus() {
    const me: { is_admin: boolean } = await api('/auth/me/');
    if (!me.is_admin) { router.replace('/dashboard'); return; }
    const current: Status = await api('/admin/backup-restore/');
    setStatus(current);
  }

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        await loadStatus();
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : 'Could not load backup status.');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  async function downloadBackup(kind: BackupKind) {
    setBusy(kind); setError(''); setMessage('');
    try {
      const prepared: { token: string } = await api('/admin/backup-restore/prepare-download/', {
        method: 'POST', body: JSON.stringify({ kind }),
      });
      // A normal HTML form lets the browser stream the attachment directly to
      // disk. We intentionally do not fetch() it into a giant in-memory Blob.
      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/backend-api/admin/backup-restore/download/';
      form.style.display = 'none';
      const token = document.createElement('input');
      token.type = 'hidden'; token.name = 'token'; token.value = prepared.token;
      form.appendChild(token);
      document.body.appendChild(form);
      form.submit();
      window.setTimeout(() => form.remove(), 1000);
      setMessage(`${kind === 'full' ? 'Full' : kind === 'media' ? 'Media' : 'Database'} backup download started.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start backup download.');
    } finally { setBusy(null); }
  }

  function chooseFile(kind: BackupKind, event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.files?.[0] || null;
    setFiles(current => ({ ...current, [kind]: next }));
    setConfirmationInputs(current => ({ ...current, [kind]: '' }));
    setError(''); setMessage('');
  }

  async function restore(kind: BackupKind) {
    const file = files[kind];
    const expected = RESTORE_CONFIRMATIONS[kind];
    if (!file || busy || confirmationInputs[kind] !== expected) return;
    const extraWarning = kind === 'media'
      ? 'This will overwrite matching media files from the backup but keep newer/unrelated media files.'
      : kind === 'full'
        ? 'This replaces tracker database data and makes the media folder match the backup. Everyone will be signed out.'
        : 'This replaces tracker database data. Everyone will be signed out. Media files are not changed.';
    if (!window.confirm(`${extraWarning}\n\nContinue with ${file.name}?`)) return;

    setBusy(kind); setError(''); setMessage('');
    try {
      const body = new FormData();
      body.append('kind', kind);
      body.append('confirmation', expected);
      body.append('backup', file);
      const result: { requires_relogin?: boolean; restored_files?: number; removed_extra_files?: number } = await api('/admin/backup-restore/restore/', {
        method: 'POST', body,
      });
      if (result.requires_relogin) {
        clearToken();
        window.location.assign(loginUrl('/backup-restore'));
        return;
      }
      setMessage(`Media restore completed. ${result.restored_files ?? 0} file${result.restored_files === 1 ? '' : 's'} restored.`);
      setFiles(current => ({ ...current, [kind]: null }));
      setConfirmationInputs(current => ({ ...current, [kind]: '' }));
      if (fileInputs[kind].current) fileInputs[kind].current!.value = '';
      await loadStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Restore failed.');
    } finally { setBusy(null); }
  }

  function RestorePanel({ kind, title, description }: { kind: BackupKind; title: string; description: string }) {
    const expected = RESTORE_CONFIRMATIONS[kind];
    return <section className="panel" style={{marginBottom: 18}}>
      <div className="panel-header">{title}</div>
      <div className="panel-body">
        <p className="muted">{description}</p>
        <div className="field" style={{marginBottom: 14}}>
          <label htmlFor={`${kind}-backup-file`}>Backup file</label>
          <input ref={fileInputs[kind]} id={`${kind}-backup-file`} className="input" type="file" accept=".tar.gz,application/gzip" disabled={busy !== null} onChange={e => chooseFile(kind, e)} />
        </div>
        {files[kind] && <div className="field" style={{marginBottom: 14}}>
          <label htmlFor={`${kind}-confirmation`}>Type <strong>{expected}</strong> to confirm</label>
          <input id={`${kind}-confirmation`} className="input" autoComplete="off" value={confirmationInputs[kind]} disabled={busy !== null} onChange={e => setConfirmationInputs(current => ({ ...current, [kind]: e.target.value }))} />
        </div>}
        <button type="button" className="button" disabled={!files[kind] || confirmationInputs[kind] !== expected || busy !== null} onClick={() => void restore(kind)}>
          {busy === kind ? 'Restoring…' : title}
        </button>
      </div>
    </section>;
  }

  if (loading) return <div className="muted">Loading backup information…</div>;

  return <div>
    <div className="page-heading-row"><div>
      <div className="eyebrow">Admin</div>
      <h1 className="page-heading">Backup &amp; Restore</h1>
      <p className="muted">Create manual local backups without keeping a second permanent backup copy on Railway. Keep downloaded backups on an ALS-controlled computer or approved storage.</p>
    </div></div>

    {error && <div className="card error" role="alert" style={{marginBottom: 16}}>{error}</div>}
    {message && <div className="card" role="status" style={{marginBottom: 16}}>{message}</div>}

    {status && <section className="panel" style={{marginBottom: 18}}>
      <div className="panel-header">Current backup information</div>
      <div className="panel-body">
        <div className="summary-grid">
          <div className="summary-card"><div className="summary-label">Media files</div><div className="summary-value">{status.media_file_count.toLocaleString('en-CA')}</div><div className="muted">{formatBytes(status.media_total_bytes)}</div></div>
          <div className="summary-card"><div className="summary-label">Database backup</div><div className="summary-value" style={{fontSize: 18}}>Tracker data</div><div className="muted">{status.migration_count} applied migrations</div></div>
          <div className="summary-card"><div className="summary-label">Media storage</div><div className="summary-value" style={{fontSize: 18}}>{status.persistent_media_volume ? 'Persistent volume' : 'Filesystem'}</div><div className="muted">{status.media_root}</div></div>
        </div>
        <p className="muted" style={{marginTop: 14}}>Database backups contain durable tracker data and password hashes, but intentionally exclude active login sessions, one-time login links, pending ticket drafts, and public rate-limit counters. Treat backup files as confidential.</p>
      </div>
    </section>}

    <section className="panel" style={{marginBottom: 18}}>
      <div className="panel-header">Download manual backup</div>
      <div className="panel-body">
        <p className="muted">The database portion may use temporary RAM/system scratch space while it is generated. Media is streamed directly from the media volume to your browser, so a full second copy of the media library is not saved on the paid Railway volume. For the cleanest Full/Media Backup, start it when staff are not actively uploading or deleting files.</p>
        <div style={{display: 'flex', flexWrap: 'wrap', gap: 10}}>
          <button type="button" className="button secondary" disabled={busy !== null} onClick={() => void downloadBackup('database')}>{busy === 'database' ? 'Preparing…' : 'Download Database Backup'}</button>
          <button type="button" className="button secondary" disabled={busy !== null} onClick={() => void downloadBackup('media')}>{busy === 'media' ? 'Preparing…' : 'Download Media Backup'}</button>
          <button type="button" className="button" disabled={busy !== null} onClick={() => void downloadBackup('full')}>{busy === 'full' ? 'Preparing…' : 'Download Full Backup'}</button>
        </div>
      </div>
    </section>

    <div className="card error" style={{marginBottom: 18}}>
      <strong>Restore is destructive.</strong> Do it when staff are not actively using the tracker. Database and Full Restore replace business data and sign everyone out. Only restore backups created by this tracker version; the backend checks the migration schema before changing data.
    </div>

    <RestorePanel kind="database" title="Restore Database" description="Restores users, tables, tickets, customers, history, tracking links, settings, and other durable tracker records. It does not change image/attachment files. Restore the matching media backup separately if needed." />
    <RestorePanel kind="media" title="Restore Media" description="Restores/overwrites files contained in a Media Backup but keeps additional files currently on the media volume. This is safer when the current database may reference newer uploads." />
    <RestorePanel kind="full" title="Restore Full Backup" description="Restores the database and media from one Full Backup. After all backup media is written successfully, media files not present in that backup are removed so the media folder matches the backup." />
  </div>;
}
