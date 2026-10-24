'use client';

import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { invokeCustomerEmail, mailtoForCustomerEmail } from '@/lib/customerEmail';
import styles from './actionRequiredEmail.module.css';

type MentionOption = {
  id: number | string;
  username: string;
  name: string;
  role_label: string;
  kind?: 'user' | 'group';
};
type Draft = {
  recipients: string[];
  mentions: string[];
  subject: string;
  body: string;
  generated_at: string;
};

export default function ActionRequiredEmailModal({ onClose }: { onClose: () => void }) {
  const [recipients, setRecipients] = useState<MentionOption[]>([]);
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<MentionOption[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [note, setNote] = useState('');
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [opened, setOpened] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        if (showSuggestions) setShowSuggestions(false);
        else onClose();
      }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose, showSuggestions]);

  useEffect(() => {
    if (!showSuggestions) return;
    let cancelled = false;
    const timeout = window.setTimeout(() => {
      api(`/problem-samples/mention-users/?q=${encodeURIComponent(query.replace(/^@/, '').trim())}`)
        .then((results: MentionOption[]) => { if (!cancelled) setSuggestions(Array.isArray(results) ? results : []); })
        .catch(() => { if (!cancelled) setSuggestions([]); });
    }, 120);
    return () => { cancelled = true; window.clearTimeout(timeout); };
  }, [query, showSuggestions]);

  function addRecipient(option: MentionOption) {
    setRecipients(previous => previous.some(selected => selected.id === option.id) ? previous : [...previous, option]);
    setQuery('');
    setDraft(null);
    setOpened(false);
    setError('');
    setShowSuggestions(false);
    input.current?.focus();
  }

  function removeRecipient(id: MentionOption['id']) {
    setRecipients(previous => previous.filter(option => option.id !== id));
    setDraft(null);
    setOpened(false);
  }

  async function preview() {
    if (!recipients.length) { setError('Add at least one recipient.'); return; }
    setError('');
    setBusy(true);
    try {
      const result: Draft = await api('/dashboard/action-required-email/', {
        method: 'POST',
        body: JSON.stringify({ recipients: recipients.map(option => `@${option.username}`), message: note }),
      });
      setDraft(result);
      setOpened(false);
      setShowSuggestions(false);
    } catch (e) {
      setDraft(null);
      setError(e instanceof Error ? e.message : 'Unable to prepare the action required update.');
    } finally {
      setBusy(false);
    }
  }

  function openEmail() {
    if (!draft) return;
    invokeCustomerEmail(mailtoForCustomerEmail({
      to: draft.recipients,
      cc: [],
      subject: draft.subject,
      body: draft.body,
    }));
    setOpened(true);
  }

  return <div className={styles.overlay} role="presentation" onMouseDown={event => {
    if (event.target === event.currentTarget) onClose();
  }}>
    <div className={styles.dialog} role="dialog" aria-modal="true" aria-labelledby="action-update-title">
      <div className={styles.titleRow}>
        <div>
          <h2 id="action-update-title">Send action required update</h2>
          <p>Share the latest Action Required counts with staff.</p>
        </div>
        <button type="button" className={styles.close} aria-label="Close email composer" onClick={onClose}>×</button>
      </div>
      {!draft ? <>
        <label className={styles.label} htmlFor="action-update-recipients">Recipients</label>
        <p className={styles.help}>Select one or more staff members or role groups such as @Lab and @CustomerService.</p>
        {recipients.length > 0 && <div className={styles.chips} aria-label="Selected recipients">
          {recipients.map(option => <span className={styles.chip} key={option.id}>
            @{option.username}
            <button type="button" aria-label={`Remove @${option.username}`} onClick={() => removeRecipient(option.id)}>×</button>
          </span>)}
        </div>}
        <div className={styles.searchWrap}>
          <input
            id="action-update-recipients"
            ref={input}
            className="input"
            autoComplete="off"
            value={query}
            placeholder="Search staff or type @Lab…"
            onChange={event => { setQuery(event.target.value); setSuggestions([]); setShowSuggestions(true); }}
            onFocus={() => setShowSuggestions(true)}
            onKeyDown={event => {
              if (event.key === 'Enter' && showSuggestions) {
                const option = suggestions.find(item => !recipients.some(selected => selected.id === item.id));
                if (option) { event.preventDefault(); addRecipient(option); }
              }
            }}
          />
          {showSuggestions && <div className={styles.suggestions} role="listbox" aria-label="Available recipients">
            {suggestions.filter(option => !recipients.some(selected => selected.id === option.id)).length ?
              suggestions.filter(option => !recipients.some(selected => selected.id === option.id)).map(option =>
                <button type="button" key={option.id} role="option" aria-selected={false}
                  onMouseDown={event => event.preventDefault()}
                  onClick={() => addRecipient(option)}>
                  <strong>{option.name}</strong>
                  <span>@{option.username}</span>
                  <small>{option.role_label}</small>
                </button>) : <div className={styles.empty}>No additional eligible recipients found.</div>}
          </div>}
        </div>
        <label className={styles.label} htmlFor="action-update-note">Additional message (optional)</label>
        <textarea id="action-update-note" className="textarea" rows={4} maxLength={2000}
          placeholder="Add an update, request, or note for your colleagues…"
          value={note} onChange={event => { setNote(event.target.value); setError(''); }} />
        <p className={styles.help}>The email will include current counts across all ticket tables and links to each Action Required queue.</p>
        {error && <p className={styles.error} role="alert">{error}</p>}
        <div className={styles.actions}>
          <button type="button" className="button" disabled={busy || !recipients.length} onClick={preview}>
            {busy ? 'Preparing…' : 'Preview email'}
          </button>
          <button type="button" className="button secondary" onClick={onClose}>Cancel</button>
        </div>
      </> : <>
        <p className={styles.help}>Review this snapshot before opening Outlook webmail. The tracker does not send it automatically.</p>
        <div className={styles.preview}>
          <div><strong>To:</strong> {draft.recipients.join(', ')}</div>
          <div><strong>Selected:</strong> {draft.mentions.join(', ')}</div>
          <label className={styles.label} htmlFor="action-update-subject">Subject</label>
          <input id="action-update-subject" className="input" value={draft.subject} readOnly />
          <label className={styles.label} htmlFor="action-update-body">Message</label>
          <textarea id="action-update-body" className="textarea" rows={13} value={draft.body} readOnly />
        </div>
        {opened && <p className={styles.success} role="status">Your mail app was opened with this draft. Please send it there to finish.</p>}
        <div className={styles.actions}>
          <button type="button" className="button" onClick={openEmail}>{opened ? 'Open email draft again' : 'Open email draft to send'}</button>
          <button type="button" className="button secondary" onClick={() => { setDraft(null); setOpened(false); }}>Edit recipients or message</button>
          <button type="button" className="button secondary" onClick={onClose}>Close</button>
        </div>
      </>}
    </div>
  </div>;
}
