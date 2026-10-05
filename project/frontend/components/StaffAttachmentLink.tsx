'use client';

import { useState } from 'react';
import { apiBlob } from '@/lib/api';

export function staffAttachmentContentPath(problemId: string | number, attachmentId: number) {
  return `/problem-samples/${encodeURIComponent(String(problemId))}/attachments/${attachmentId}/content/`;
}

type Props = {
  problemId: string | number;
  attachmentId: number;
  filename: string;
  className?: string;
  children?: React.ReactNode;
};

export default function StaffAttachmentLink({ problemId, attachmentId, filename, className = 'attachment-link', children }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function download() {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const blob = await apiBlob(staffAttachmentContentPath(problemId, attachmentId));
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename || `attachment-${attachmentId}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Attachment unavailable');
    } finally {
      setBusy(false);
    }
  }

  return <span className="staff-attachment-download">
    <button type="button" className={className} onClick={download} disabled={busy}>{busy ? 'Downloading…' : (children || filename || 'Download')}</button>
    {error && <span className="staff-attachment-error">{error}</span>}
  </span>;
}
