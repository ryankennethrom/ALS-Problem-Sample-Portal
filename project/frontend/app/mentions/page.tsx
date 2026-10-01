'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import MentionText from '@/components/MentionText';

type Mention = {
  id: number;
  ticket_id: string;
  problem_number: number;
  table_name: string;
  comment: string;
  mentioned_by_username: string;
  mentioned_by_name: string;
  created_at: string;
  read_at: string | null;
};

type MentionInbox = {
  unread_count: number;
  results: Mention[];
};

export default function MentionsPage() {
  const router = useRouter();
  const [data, setData] = useState<MentionInbox>({ unread_count: 0, results: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [markingAll, setMarkingAll] = useState(false);

  async function load() {
    setLoading(true);
    setError('');
    try {
      const result: MentionInbox = await api('/problem-samples/mentions/');
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load mentions');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function notifyBadgeChanged() {
    if (typeof window !== 'undefined') window.dispatchEvent(new Event('mentions-updated'));
  }

  async function openMention(mention: Mention) {
    try {
      if (!mention.read_at) {
        await api(`/problem-samples/mentions/${mention.id}/read/`, { method: 'POST' });
        notifyBadgeChanged();
      }
    } finally {
      router.push(`/problems/${mention.ticket_id}#follow-ups`);
    }
  }

  async function markAllRead() {
    setMarkingAll(true);
    try {
      await api('/problem-samples/mentions/mark-all-read/', { method: 'POST', successMessage: 'Mentions marked as read.' });
      setData(current => ({
        unread_count: 0,
        results: current.results.map(item => ({ ...item, read_at: item.read_at || new Date().toISOString() })),
      }));
      notifyBadgeChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not mark mentions as read');
    } finally {
      setMarkingAll(false);
    }
  }

  return <div>
    <div className="page-header mention-page-header">
      <div>
        <h1>Mentions</h1>
        <p className="muted">Follow-up comments where another staff member mentioned your @username.</p>
      </div>
      {data.unread_count > 0 && <button type="button" className="button secondary" onClick={markAllRead} disabled={markingAll}>{markingAll ? 'Marking…' : 'Mark all read'}</button>}
    </div>

    {error && <div className="card error" style={{marginBottom:14}}>{error}</div>}
    <section className="panel">
      <div className="panel-header"><strong>Your mentions</strong><span className="history-count">{data.unread_count} unread</span></div>
      <div className="panel-body mention-inbox-list">
        {loading && <div className="muted">Loading mentions…</div>}
        {!loading && data.results.length === 0 && <div className="muted">You have not been mentioned yet.</div>}
        {!loading && data.results.map(mention => <article key={mention.id} className={`mention-inbox-item ${mention.read_at ? '' : 'unread'}`}>
          <div className="mention-inbox-topline">
            <div>
              <strong>Ticket #{mention.problem_number}</strong>{mention.table_name ? <span className="muted"> · {mention.table_name}</span> : null}
            </div>
            {!mention.read_at && <span className="mention-unread-badge">Unread</span>}
          </div>
          <div className="mention-inbox-comment"><MentionText text={mention.comment} /></div>
          <div className="mention-inbox-meta">
            Mentioned by {mention.mentioned_by_name}{mention.mentioned_by_username ? ` (@${mention.mentioned_by_username})` : ''} · {new Date(mention.created_at).toLocaleString()}
          </div>
          <div className="mention-inbox-actions"><button type="button" className="button secondary" onClick={() => openMention(mention)}>Open ticket</button></div>
        </article>)}
      </div>
    </section>
  </div>;
}
