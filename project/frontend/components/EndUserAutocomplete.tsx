'use client';

import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';

type EndUserSuggestion = {
  id: number;
  external_customer_id: string;
  company_name: string;
  customer_type: string;
  brand: string;
  city: string;
  state: string;
  email: string;
  match_score?: number;
};

export default function EndUserAutocomplete({
  value,
  onChange,
  label,
  required = false,
  id = 'end-user-autocomplete',
  placeholder = 'Start typing an end user company…',
}: {
  value: unknown;
  onChange: (value: string) => void;
  label?: string;
  required?: boolean;
  id?: string;
  placeholder?: string;
}) {
  const text = value == null ? '' : String(value);
  const [suggestions, setSuggestions] = useState<EndUserSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [searchEnabled, setSearchEnabled] = useState(false);
  const requestId = useRef(0);

  useEffect(() => {
    if (!searchEnabled) {
      setSuggestions([]);
      setOpen(false);
      setLoading(false);
      return;
    }

    const query = text.trim();
    if (!query) {
      setSuggestions([]);
      setOpen(false);
      return;
    }

    const currentRequest = ++requestId.current;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        const data = await api(`/customers/end-users/suggest/?q=${encodeURIComponent(query)}`);
        if (currentRequest !== requestId.current) return;
        setSuggestions(Array.isArray(data) ? data : []);
        setOpen(true);
      } catch {
        if (currentRequest === requestId.current) {
          setSuggestions([]);
          setOpen(false);
        }
      } finally {
        if (currentRequest === requestId.current) setLoading(false);
      }
    }, 180);

    return () => window.clearTimeout(timer);
  }, [text, searchEnabled]);

  function choose(item: EndUserSuggestion) {
    onChange(item.company_name);
    setSuggestions([]);
    setOpen(false);
    setSearchEnabled(false);
  }

  return <div className="field distributor-field">
    {label && <label htmlFor={id}>{label}{required && <span className="required-marker" aria-hidden="true"> *</span>}</label>}
    <div className="distributor-autocomplete">
      <input
        id={id}
        className="input"
        value={text}
        required={required}
        autoComplete="off"
        placeholder={placeholder}
        onFocus={() => {
          setSearchEnabled(true);
          if (suggestions.length) setOpen(true);
        }}
        onBlur={() => window.setTimeout(() => {
          setOpen(false);
          setSearchEnabled(false);
          requestId.current += 1;
        }, 140)}
        onChange={e => {
          setSearchEnabled(true);
          onChange(e.target.value);
        }}
      />
      {loading && <span className="distributor-loading">Searching…</span>}
      {open && <div className="distributor-suggestions" role="listbox">
        {suggestions.length ? suggestions.map(item => <button
          type="button"
          className="distributor-suggestion"
          key={`${item.id}-${item.external_customer_id}`}
          onMouseDown={e => e.preventDefault()}
          onClick={() => choose(item)}
        >
          <span className="distributor-company">{item.company_name}</span>
          <span className="distributor-meta">
            {item.external_customer_id && <span className="distributor-meta-item"><strong>CoyId</strong> {item.external_customer_id}</span>}
            {item.city && <span className="distributor-meta-item"><strong>City</strong> {item.city}</span>}
            {item.state && <span className="distributor-meta-item"><strong>State</strong> {item.state}</span>}
            {item.brand && <span className="distributor-meta-item distributor-meta-brand"><strong>Brand</strong> {item.brand}</span>}
          </span>
        </button>) : <div className="distributor-empty">No end user companies found</div>}
      </div>}
    </div>
    <div className="muted result-meta">Fuzzy suggestions are limited to customer records where CoyType is End User.</div>
  </div>;
}
