'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';

type ClientEmailSuggestion = {
  id: number;
  external_customer_id: string;
  company_name: string;
  customer_type: string;
  brand: string;
  city: string;
  state: string;
  primary_contact: string;
  email: string;
  match_score?: number;
};

type DependencyValue = {
  id?: string;
  label: string;
  value: unknown;
};

type SuggestResponse = {
  results: ClientEmailSuggestion[];
  active_company: string;
  active_priority: number | null;
  attempted_companies: string[];
};

function normalizeEmailList(value: unknown): string[] {
  const raw = Array.isArray(value) ? value : (typeof value === 'string' && value.trim() ? [value] : []);
  const seen = new Set<string>();
  const result: string[] = [];
  for (const item of raw) {
    const email = String(item ?? '').trim();
    const key = email.toLowerCase();
    if (!email || seen.has(key)) continue;
    seen.add(key);
    result.push(email);
  }
  return result;
}

function looksLikeEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

export default function ClientEmailAutocomplete({
  value,
  onChange,
  label,
  required = false,
  id = 'client-email-list',
  placeholder = 'Filter emails or contact names…',
  dependencies = [],
}: {
  value: unknown;
  onChange: (value: string[]) => void;
  label?: string;
  required?: boolean;
  id?: string;
  placeholder?: string;
  dependencies?: DependencyValue[];
}) {
  const emails = useMemo(() => normalizeEmailList(value), [value]);
  const valueIsUninitialized = value === null || value === undefined || value === '';
  const configuredDependencies = useMemo(
    () => dependencies.map((item, index) => ({
      ...item,
      priority: index + 1,
      company: item.value == null ? '' : String(item.value).trim(),
    })),
    [dependencies],
  );
  const populatedDependencies = useMemo(
    () => configuredDependencies.filter(item => item.company),
    [configuredDependencies],
  );
  const dependencyConfigured = configuredDependencies.length > 0;

  const [sourceSuggestions, setSourceSuggestions] = useState<ClientEmailSuggestion[]>([]);
  const [filteredSuggestions, setFilteredSuggestions] = useState<ClientEmailSuggestion[]>([]);
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeCompany, setActiveCompany] = useState('');
  const [attemptedCompanies, setAttemptedCompanies] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);
  const [newEmail, setNewEmail] = useState('');
  const [addError, setAddError] = useState('');
  const sourceRequestId = useRef(0);
  const filterRequestId = useRef(0);
  const hydratedDependencySignature = useRef('');
  const onChangeRef = useRef(onChange);

  useEffect(() => { onChangeRef.current = onChange; }, [onChange]);

  const dependencySignature = populatedDependencies.map(item => `${item.id || item.label}:${item.company.toLowerCase()}`).join('|');

  useEffect(() => {
    setSelected(new Set());
    setDismissed(new Set());
    setFilter('');
  }, [dependencySignature]);

  // Load the complete candidate list for the active dependency. An untouched
  // Client Email value uses '' as an "uninitialized" sentinel; once the user
  // edits the list it becomes an array, including [] after Clear All. That
  // lets us populate a new dependency once without resurrecting deleted emails.
  useEffect(() => {
    if (!dependencyConfigured || populatedDependencies.length === 0) {
      setSourceSuggestions([]);
      setActiveCompany('');
      setAttemptedCompanies([]);
      hydratedDependencySignature.current = '';
      return;
    }

    const currentRequest = ++sourceRequestId.current;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        for (const dependency of populatedDependencies) params.append('company', dependency.company);
        const raw = await api(`/customers/client-emails/suggest/?${params.toString()}`);
        if (currentRequest !== sourceRequestId.current) return;
        const data: SuggestResponse = Array.isArray(raw)
          ? { results: raw, active_company: '', active_priority: null, attempted_companies: [] }
          : raw;
        const results = Array.isArray(data?.results) ? data.results : [];
        setSourceSuggestions(results);
        setActiveCompany(data?.active_company || '');
        setAttemptedCompanies(Array.isArray(data?.attempted_companies) ? data.attempted_companies : []);

        if (valueIsUninitialized && hydratedDependencySignature.current !== dependencySignature) {
          hydratedDependencySignature.current = dependencySignature;
          onChangeRef.current(normalizeEmailList(results.map(item => item.email)));
        }
      } catch {
        if (currentRequest === sourceRequestId.current) {
          setSourceSuggestions([]);
          setActiveCompany('');
          setAttemptedCompanies([]);
        }
      } finally {
        if (currentRequest === sourceRequestId.current) setLoading(false);
      }
    }, 80);

    return () => window.clearTimeout(timer);
  }, [dependencyConfigured, dependencySignature, valueIsUninitialized]);

  // Fuzzy filtering stays a search aid rather than the value editor itself.
  // Scoped fields intersect fuzzy results with the current kept list, so
  // previously deleted addresses do not reappear just because the query changes.
  useEffect(() => {
    const query = filter.trim();
    if (!query) {
      setFilteredSuggestions([]);
      return;
    }
    if (dependencyConfigured && populatedDependencies.length === 0) {
      setFilteredSuggestions([]);
      return;
    }

    const currentRequest = ++filterRequestId.current;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams({ q: query });
        for (const dependency of populatedDependencies) params.append('company', dependency.company);
        const raw = await api(`/customers/client-emails/suggest/?${params.toString()}`);
        if (currentRequest !== filterRequestId.current) return;
        const data: SuggestResponse = Array.isArray(raw)
          ? { results: raw, active_company: '', active_priority: null, attempted_companies: [] }
          : raw;
        setFilteredSuggestions(Array.isArray(data?.results) ? data.results : []);
        if (data?.active_company) setActiveCompany(data.active_company);
        if (Array.isArray(data?.attempted_companies)) setAttemptedCompanies(data.attempted_companies);
      } catch {
        if (currentRequest === filterRequestId.current) setFilteredSuggestions([]);
      } finally {
        if (currentRequest === filterRequestId.current) setLoading(false);
      }
    }, 180);

    return () => window.clearTimeout(timer);
  }, [filter, dependencyConfigured, dependencySignature]);

  const metadataByEmail = useMemo(() => {
    const map = new Map<string, ClientEmailSuggestion>();
    for (const item of [...sourceSuggestions, ...filteredSuggestions]) {
      if (item.email) map.set(item.email.toLowerCase(), item);
    }
    return map;
  }, [sourceSuggestions, filteredSuggestions]);

  const visibleRows = useMemo(() => {
    const query = filter.trim().toLowerCase();
    const currentKeys = new Set(emails.map(email => email.toLowerCase()));

    if (!query) {
      return emails.map(email => ({ email, suggestion: metadataByEmail.get(email.toLowerCase()), stored: true }));
    }

    const rankedKeys = new Set(filteredSuggestions.map(item => item.email.toLowerCase()));
    const rows: { email: string; suggestion?: ClientEmailSuggestion; stored: boolean }[] = [];
    const seen = new Set<string>();

    // Use backend fuzzy ranking first.
    for (const item of filteredSuggestions) {
      const key = item.email.toLowerCase();
      if (dependencyConfigured && !currentKeys.has(key)) continue;
      if (dismissed.has(key) || seen.has(key)) continue;
      seen.add(key);
      rows.push({ email: item.email, suggestion: item, stored: currentKeys.has(key) });
    }

    // Keep manually-added / historical emails searchable even when they are not
    // present in the latest customer export.
    for (const email of emails) {
      const key = email.toLowerCase();
      if (dismissed.has(key) || seen.has(key)) continue;
      const meta = metadataByEmail.get(key);
      const localHaystack = `${email} ${meta?.primary_contact || ''} ${meta?.company_name || ''}`.toLowerCase();
      if (localHaystack.includes(query) || rankedKeys.has(key)) {
        seen.add(key);
        rows.push({ email, suggestion: meta, stored: true });
      }
    }

    // An unscoped field uses fuzzy search as the discovery mechanism. Those
    // results can be selected and committed with Keep Selected.
    if (!dependencyConfigured) {
      for (const item of filteredSuggestions) {
        const key = item.email.toLowerCase();
        if (dismissed.has(key) || seen.has(key)) continue;
        seen.add(key);
        rows.push({ email: item.email, suggestion: item, stored: currentKeys.has(key) });
      }
    }

    return rows;
  }, [emails, filter, filteredSuggestions, metadataByEmail, dependencyConfigured, dismissed]);

  function toggle(email: string) {
    const key = email.toLowerCase();
    setSelected(current => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }

  function keepSelected() {
    if (!selected.size) return;
    const kept = visibleRows.filter(row => selected.has(row.email.toLowerCase())).map(row => row.email);
    onChange(normalizeEmailList(kept));
    setSelected(new Set());
    setDismissed(new Set());
    setFilter('');
  }

  function deleteSelected() {
    if (!selected.size) return;
    onChange(emails.filter(email => !selected.has(email.toLowerCase())));
    setDismissed(current => new Set([...current, ...selected]));
    setSelected(new Set());
  }

  function deleteAll() {
    onChange([]);
    setSelected(new Set());
    setDismissed(new Set());
    setFilter('');
  }

  function addEmail() {
    const email = newEmail.trim();
    if (!looksLikeEmail(email)) {
      setAddError('Enter a valid email address.');
      return;
    }
    if (emails.some(item => item.toLowerCase() === email.toLowerCase())) {
      setAddError('That email is already in the list.');
      return;
    }
    onChange([...emails, email]);
    setDismissed(current => { const next = new Set(current); next.delete(email.toLowerCase()); return next; });
    setNewEmail('');
    setAddError('');
    setAdding(false);
  }

  const activeDependency = activeCompany
    ? configuredDependencies.find(item => item.company.toLowerCase() === activeCompany.toLowerCase())
    : undefined;

  let helper = 'Type in Filter to fuzzy-search imported email addresses and contact names. Use the list controls to choose which addresses are kept on this row.';
  if (dependencyConfigured) {
    if (populatedDependencies.length === 0) {
      helper = `Enter a company in one of the configured dependency fields to load suggested emails: ${configuredDependencies.map(item => item.label).join(', ')}. You can still add an email manually.`;
    } else if (activeCompany) {
      const source = activeDependency ? `Priority ${activeDependency.priority} — ${activeDependency.label}` : 'active dependency';
      helper = `Loaded from ${source}: ${activeCompany}. The first dependency with available emails is used; Filter fuzzy-narrows the visible list without re-adding deleted addresses.`;
    } else if (attemptedCompanies.length) {
      helper = `No imported emails were found under ${attemptedCompanies.join(', ')}. You can add an email manually.`;
    }
  }

  return <div className="field client-email-field">
    {label && <label htmlFor={`${id}-filter`}>{label}{required && <span className="required-marker" aria-hidden="true"> *</span>}</label>}
    <div className="client-email-editor">
      <div className="client-email-toolbar-top">
        <div className="client-email-filter-wrap">
          <input
            id={`${id}-filter`}
            className="input"
            type="search"
            value={filter}
            autoComplete="off"
            placeholder={placeholder}
            onChange={event => setFilter(event.target.value)}
          />
          {loading && <span className="client-email-loading">Searching…</span>}
        </div>
        <span className="client-email-count">{emails.length} email{emails.length === 1 ? '' : 's'}</span>
      </div>

      <div className="client-email-list" role="listbox" aria-multiselectable="true">
        {visibleRows.length ? visibleRows.map(row => {
          const key = row.email.toLowerCase();
          const item = row.suggestion;
          return <label className={`client-email-list-row${selected.has(key) ? ' selected' : ''}`} key={key}>
            <input type="checkbox" checked={selected.has(key)} onChange={() => toggle(row.email)} />
            <span className="client-email-list-copy">
              <span className="client-email-address">{row.email}</span>
              <span className="client-email-meta">
                {item
                  ? [item.primary_contact, item.company_name, item.external_customer_id && `CoyId ${item.external_customer_id}`, item.city, item.state].filter(Boolean).join(' · ')
                  : 'Added manually or retained from an earlier customer export'}
              </span>
            </span>
            {!row.stored && <span className="client-email-suggestion-badge">Suggestion</span>}
          </label>;
        }) : <div className="client-email-empty">
          {filter.trim()
            ? 'No matching emails found.'
            : dependencyConfigured && populatedDependencies.length === 0
              ? 'Select a dependency company or add an email manually.'
              : 'No client emails are currently kept.'}
        </div>}
      </div>

      <div className="client-email-actions">
        <button type="button" className="button secondary" onClick={keepSelected} disabled={!selected.size}>Keep Selected</button>
        <button type="button" className="button secondary" onClick={deleteSelected} disabled={!selected.size}>Delete Selected</button>
        <button type="button" className="button danger" onClick={deleteAll} disabled={!emails.length}>Clear All</button>
        <button type="button" className="button secondary" onClick={() => { setAdding(current => !current); setAddError(''); }}>+ Add an Email</button>
      </div>

      {adding && <div className="client-email-add-row">
        <input
          className="input"
          type="email"
          value={newEmail}
          placeholder="name@example.com"
          onChange={event => { setNewEmail(event.target.value); setAddError(''); }}
          onKeyDown={event => {
            if (event.key === 'Enter') {
              event.preventDefault();
              addEmail();
            }
          }}
          autoFocus
        />
        <button type="button" className="button" onClick={addEmail}>Add</button>
        <button type="button" className="button secondary" onClick={() => { setAdding(false); setNewEmail(''); setAddError(''); }}>Cancel</button>
        {addError && <div className="client-email-add-error">{addError}</div>}
      </div>}
    </div>
    <div className="muted result-meta">{helper}</div>
  </div>;
}
