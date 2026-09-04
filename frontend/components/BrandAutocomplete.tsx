'use client';

import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';

type BrandSuggestion = {
  brand: string;
  match_score?: number;
  customer_count?: number;
  company_examples?: string[];
};

export default function BrandAutocomplete({
  value,
  onChange,
  label,
  required = false,
  id = 'brand-autocomplete',
  placeholder = 'Start typing a brand…',
}: {
  value: unknown;
  onChange: (value: string) => void;
  label?: string;
  required?: boolean;
  id?: string;
  placeholder?: string;
}) {
  const text = value == null ? '' : String(value);
  const [suggestions, setSuggestions] = useState<BrandSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const requestId = useRef(0);

  useEffect(() => {
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
        const data = await api(`/customers/brands/suggest/?q=${encodeURIComponent(query)}`);
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
  }, [text]);

  function choose(item: BrandSuggestion) {
    onChange(item.brand);
    setSuggestions([]);
    setOpen(false);
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
        onFocus={() => { if (suggestions.length) setOpen(true); }}
        onBlur={() => window.setTimeout(() => setOpen(false), 140)}
        onChange={e => onChange(e.target.value)}
      />
      {loading && <span className="distributor-loading">Searching…</span>}
      {open && <div className="distributor-suggestions" role="listbox">
        {suggestions.length ? suggestions.map(item => <button
          type="button"
          className="distributor-suggestion"
          key={item.brand.toLowerCase()}
          onMouseDown={e => e.preventDefault()}
          onClick={() => choose(item)}
        >
          <span className="distributor-company">{item.brand}</span>
          <span className="distributor-meta">
            {typeof item.customer_count === 'number' && <span className="distributor-meta-item"><strong>Customer records</strong> {item.customer_count}</span>}
            {!!item.company_examples?.length && <span className="distributor-meta-item distributor-meta-brand"><strong>Examples</strong> {item.company_examples.join(', ')}</span>}
          </span>
        </button>) : <div className="distributor-empty">No brands found</div>}
      </div>}
    </div>
    <div className="muted result-meta">Fuzzy suggestions come from Brand values in the current Customer Export.</div>
  </div>;
}
