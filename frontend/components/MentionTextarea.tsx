'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';

type MentionUser = {
  id: number | string;
  username: string;
  name: string;
  role_label: string;
  kind?: 'user' | 'group';
};

type ActiveMention = {
  start: number;
  end: number;
  query: string;
};

function activeMention(value: string, caret: number): ActiveMention | null {
  const before = value.slice(0, caret);
  const match = before.match(/(^|[\s([{:;,])@([A-Za-z0-9_.+-]*)$/);
  if (!match) return null;
  const query = match[2] || '';
  const start = caret - query.length - 1;
  return { start, end: caret, query };
}

export default function MentionTextarea({
  value,
  onChange,
  placeholder = 'Add follow-up…',
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  const ref = useRef<HTMLTextAreaElement | null>(null);
  const [caret, setCaret] = useState(0);
  const [suggestions, setSuggestions] = useState<MentionUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const mention = useMemo(() => activeMention(value, caret), [value, caret]);

  useEffect(() => {
    if (!mention) {
      setSuggestions([]);
      setSelectedIndex(0);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        const data = await api(`/problem-samples/mention-users/?q=${encodeURIComponent(mention.query)}`);
        if (!cancelled) {
          setSuggestions(Array.isArray(data) ? data : []);
          setSelectedIndex(0);
        }
      } catch {
        if (!cancelled) setSuggestions([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 120);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [mention?.query, mention?.start]);

  function updateCaret(target: HTMLTextAreaElement) {
    setCaret(target.selectionStart ?? target.value.length);
  }

  function choose(user: MentionUser) {
    if (!mention) return;
    const before = value.slice(0, mention.start);
    const after = value.slice(mention.end);
    const insertion = `@${user.username} `;
    const next = `${before}${insertion}${after}`;
    const nextCaret = before.length + insertion.length;
    onChange(next);
    setSuggestions([]);
    setCaret(nextCaret);
    window.requestAnimationFrame(() => {
      ref.current?.focus();
      ref.current?.setSelectionRange(nextCaret, nextCaret);
    });
  }

  return <div className="mention-composer">
    <textarea
      ref={ref}
      className="textarea"
      placeholder={placeholder}
      value={value}
      onChange={event => {
        onChange(event.target.value);
        updateCaret(event.target);
      }}
      onClick={event => updateCaret(event.currentTarget)}
      onKeyUp={event => {
        if (!['ArrowDown', 'ArrowUp', 'Enter', 'Escape'].includes(event.key)) updateCaret(event.currentTarget);
      }}
      onKeyDown={event => {
        if (!mention || suggestions.length === 0) return;
        if (event.key === 'ArrowDown') {
          event.preventDefault();
          setSelectedIndex(index => (index + 1) % suggestions.length);
        } else if (event.key === 'ArrowUp') {
          event.preventDefault();
          setSelectedIndex(index => (index - 1 + suggestions.length) % suggestions.length);
        } else if (event.key === 'Enter') {
          event.preventDefault();
          choose(suggestions[selectedIndex]);
        } else if (event.key === 'Escape') {
          event.preventDefault();
          setSuggestions([]);
        }
      }}
    />
    {mention && (loading || suggestions.length > 0) && <div className="mention-suggestions" role="listbox" aria-label="Mention staff or a staff group">
      {loading && suggestions.length === 0 && <div className="mention-suggestion-empty">Finding staff…</div>}
      {suggestions.map((user, index) => <button
        key={user.id}
        type="button"
        role="option"
        aria-selected={index === selectedIndex}
        className={`mention-suggestion ${index === selectedIndex ? 'active' : ''}`}
        onMouseDown={event => event.preventDefault()}
        onClick={() => choose(user)}
      >
        <span className="mention-suggestion-name">{user.name}</span>
        <span className="mention-suggestion-username">@{user.username}</span>
        {user.role_label && <span className="mention-suggestion-role">{user.role_label}</span>}
      </button>)}
    </div>}
    <div className="muted mention-help">Type <strong>@</strong> to mention staff, <strong>@Lab</strong>, or <strong>@CustomerService</strong>. Only staff with an ALS email receive individual mentions.</div>
  </div>;
}
