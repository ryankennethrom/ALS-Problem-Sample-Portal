'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { ProblemColumn, ProblemTable } from '@/lib/problemTables';

export type MatchMode = 'all' | 'any';

export type AdvancedFilter = {
  field_key: string;
  operator: string;
  value?: string | boolean;
  value2?: string | boolean;
};

type DraftCondition = AdvancedFilter & { id: string };

type Operator = { value: string; label: string };

const TEXT_OPERATORS: Operator[] = [
  { value: 'contains', label: 'Contains' },
  { value: 'not_contains', label: 'Does not contain' },
  { value: 'equals', label: 'Equals' },
  { value: 'not_equals', label: 'Does not equal' },
  { value: 'starts_with', label: 'Starts with' },
  { value: 'ends_with', label: 'Ends with' },
  { value: 'is_empty', label: 'Is empty' },
  { value: 'is_not_empty', label: 'Is not empty' },
];

const NUMBER_OPERATORS: Operator[] = [
  { value: 'equals', label: 'Equals' },
  { value: 'not_equals', label: 'Does not equal' },
  { value: 'gt', label: 'Greater than' },
  { value: 'gte', label: 'Greater than or equal to' },
  { value: 'lt', label: 'Less than' },
  { value: 'lte', label: 'Less than or equal to' },
  { value: 'between', label: 'Between' },
  { value: 'is_empty', label: 'Is empty' },
  { value: 'is_not_empty', label: 'Is not empty' },
];

const CHOICE_OPERATORS: Operator[] = [
  { value: 'equals', label: 'Is' },
  { value: 'not_equals', label: 'Is not' },
  { value: 'is_empty', label: 'Is empty' },
  { value: 'is_not_empty', label: 'Is not empty' },
];

const MULTI_CHOICE_OPERATORS: Operator[] = [
  { value: 'contains', label: 'Contains' },
  { value: 'not_contains', label: 'Does not contain' },
  { value: 'is_empty', label: 'Is empty' },
  { value: 'is_not_empty', label: 'Is not empty' },
];

const TEMPORAL_OPERATORS: Operator[] = [
  { value: 'equals', label: 'Is' },
  { value: 'not_equals', label: 'Is not' },
  { value: 'before', label: 'Is before' },
  { value: 'after', label: 'Is after' },
  { value: 'between', label: 'Is between' },
  { value: 'is_empty', label: 'Is empty' },
  { value: 'is_not_empty', label: 'Is not empty' },
];

const BOOLEAN_OPERATORS: Operator[] = [{ value: 'equals', label: 'Is' }];
const VALUELESS_OPERATORS = new Set(['is_empty', 'is_not_empty']);

function operatorsFor(column: ProblemColumn): Operator[] {
  switch (column.column_type) {
    case 'number': return NUMBER_OPERATORS;
    case 'choice': return CHOICE_OPERATORS;
    case 'group': return CHOICE_OPERATORS;
    case 'multi_choice': return MULTI_CHOICE_OPERATORS;
    case 'date':
    case 'datetime':
    case 'time': return TEMPORAL_OPERATORS;
    case 'boolean': return BOOLEAN_OPERATORS;
    default: return TEXT_OPERATORS;
  }
}

function makeId() {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
}

function defaultValueFor(column: ProblemColumn): string | boolean {
  return column.column_type === 'boolean' ? true : '';
}

function createCondition(column: ProblemColumn): DraftCondition {
  const operator = operatorsFor(column)[0]?.value || 'equals';
  return {
    id: makeId(),
    field_key: column.field_key,
    operator,
    value: defaultValueFor(column),
    value2: '',
  };
}

function inputType(column: ProblemColumn) {
  switch (column.column_type) {
    case 'number': return 'number';
    case 'date': return 'date';
    case 'datetime': return 'datetime-local';
    case 'time': return 'time';
    case 'email':
    case 'client_email':
    case 'row_creator':
    case 'recent_row_modifier': return 'email';
    case 'url': return 'url';
    default: return 'text';
  }
}

type AdvancedSuggestion = {
  key: string;
  value: string;
  title: string;
  meta: string[];
};

function usesFuzzySuggestions(column: ProblemColumn): boolean {
  return ['distributor', 'end_user', 'brand', 'client_email'].includes(column.column_type);
}

function suggestionEndpoint(column: ProblemColumn, query: string): string {
  const q = encodeURIComponent(query);
  switch (column.column_type) {
    case 'distributor': return `/customers/distributors/suggest/?q=${q}`;
    case 'end_user': return `/customers/end-users/suggest/?q=${q}`;
    case 'brand': return `/customers/brands/suggest/?q=${q}`;
    case 'client_email': return `/customers/client-emails/suggest/?q=${q}`;
    default: return '';
  }
}

function normalizeSuggestions(column: ProblemColumn, raw: unknown): AdvancedSuggestion[] {
  const source = column.column_type === 'client_email' && raw && !Array.isArray(raw)
    ? (raw as { results?: unknown[] }).results || []
    : raw;
  if (!Array.isArray(source)) return [];

  const seen = new Set<string>();
  const result: AdvancedSuggestion[] = [];
  for (const item of source) {
    if (!item || typeof item !== 'object') continue;
    const data = item as Record<string, unknown>;
    let value = '';
    let title = '';
    const meta: string[] = [];

    if (column.column_type === 'brand') {
      value = String(data.brand || '').trim();
      title = value;
      if (typeof data.customer_count === 'number') meta.push(`${data.customer_count} customer record${data.customer_count === 1 ? '' : 's'}`);
      if (Array.isArray(data.company_examples) && data.company_examples.length) meta.push(`Examples: ${data.company_examples.map(String).join(', ')}`);
    } else if (column.column_type === 'client_email') {
      value = String(data.email || '').trim();
      title = value;
      if (data.primary_contact) meta.push(String(data.primary_contact));
      if (data.company_name) meta.push(String(data.company_name));
      const place = [data.city, data.state].filter(Boolean).map(String).join(', ');
      if (place) meta.push(place);
    } else {
      value = String(data.company_name || '').trim();
      title = value;
      if (data.external_customer_id) meta.push(`CoyId ${String(data.external_customer_id)}`);
      const place = [data.city, data.state].filter(Boolean).map(String).join(', ');
      if (place) meta.push(place);
      if (data.brand) meta.push(`Brand ${String(data.brand)}`);
    }

    const key = value.toLowerCase();
    if (!value || seen.has(key)) continue;
    seen.add(key);
    result.push({ key, value, title, meta });
  }
  return result;
}

function AdvancedSuggestionInput({
  column,
  value,
  placeholder,
  onChange,
}: {
  column: ProblemColumn;
  value: string | boolean | undefined;
  placeholder: string;
  onChange: (value: string) => void;
}) {
  const text = value == null ? '' : String(value);
  const [suggestions, setSuggestions] = useState<AdvancedSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [searchEnabled, setSearchEnabled] = useState(false);
  const requestId = useRef(0);

  useEffect(() => {
    if (!searchEnabled) {
      setOpen(false);
      setLoading(false);
      return;
    }
    const query = text.trim();
    if (!query) {
      setSuggestions([]);
      setOpen(false);
      setLoading(false);
      return;
    }

    const endpoint = suggestionEndpoint(column, query);
    if (!endpoint) return;
    const currentRequest = ++requestId.current;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        const raw = await api(endpoint);
        if (currentRequest !== requestId.current) return;
        setSuggestions(normalizeSuggestions(column, raw));
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
  }, [column, searchEnabled, text]);

  function choose(suggestion: AdvancedSuggestion) {
    requestId.current += 1;
    setSearchEnabled(false);
    setSuggestions([]);
    setOpen(false);
    onChange(suggestion.value);
  }

  return <div className="advanced-suggestion-input distributor-autocomplete advanced-value">
    <input
      className="input advanced-value"
      type={column.column_type === 'client_email' ? 'email' : 'text'}
      value={text}
      autoComplete="off"
      placeholder={placeholder}
      onFocus={() => {
        setSearchEnabled(true);
        if (suggestions.length) setOpen(true);
      }}
      onBlur={() => window.setTimeout(() => {
        requestId.current += 1;
        setSearchEnabled(false);
        setOpen(false);
      }, 140)}
      onChange={event => {
        setSearchEnabled(true);
        onChange(event.target.value);
      }}
    />
    {loading && <span className="distributor-loading">Searching…</span>}
    {open && <div className="distributor-suggestions advanced-suggestions" role="listbox">
      {suggestions.length ? suggestions.map(suggestion => <button
        type="button"
        className="distributor-suggestion"
        key={suggestion.key}
        onMouseDown={event => event.preventDefault()}
        onClick={() => choose(suggestion)}
      >
        <span className="distributor-company">{suggestion.title}</span>
        {!!suggestion.meta.length && <span className="distributor-meta">{suggestion.meta.map((item, index) => <span className="distributor-meta-item" key={`${suggestion.key}-${index}`}>{item}</span>)}</span>}
      </button>) : <div className="distributor-empty">No suggestions found</div>}
    </div>}
  </div>;
}

function FilterValue({
  column,
  condition,
  second = false,
  onChange,
}: {
  column: ProblemColumn;
  condition: DraftCondition;
  second?: boolean;
  onChange: (value: string | boolean) => void;
}) {
  const value = second ? condition.value2 : condition.value;

  if (column.column_type === 'boolean') {
    return <select className="select advanced-value" value={String(value ?? true)} onChange={e => onChange(e.target.value === 'true')}>
      <option value="true">Yes</option>
      <option value="false">No</option>
    </select>;
  }

  if (column.column_type === 'group') {
    return <select className="select advanced-value" value={String(value ?? '')} onChange={e => onChange(e.target.value)}>
      <option value="">Select a user…</option>
      {(column.group_users || []).map(user => <option key={user.id} value={user.email}>{user.name && user.name.toLowerCase() !== user.email.toLowerCase() ? `${user.name} (${user.email})` : user.email}</option>)}
    </select>;
  }

  if (column.column_type === 'choice' || column.column_type === 'multi_choice') {
    return <select className="select advanced-value" value={String(value ?? '')} onChange={e => onChange(e.target.value)}>
      <option value="">Select a value…</option>
      {column.choices.map(choice => <option key={choice} value={choice}>{choice}</option>)}
    </select>;
  }

  if (usesFuzzySuggestions(column)) {
    return <AdvancedSuggestionInput
      column={column}
      value={value}
      placeholder={second ? 'Second value' : 'Type to search suggestions…'}
      onChange={next => onChange(next)}
    />;
  }

  return <input
    className="input advanced-value"
    type={inputType(column)}
    step={column.column_type === 'number' ? 'any' : undefined}
    value={String(value ?? '')}
    placeholder={second ? 'Second value' : 'Value'}
    onChange={e => onChange(e.target.value)}
  />;
}

export default function AdvancedSearch({
  table,
  activeCount,
  onApply,
  onClear,
}: {
  table: ProblemTable;
  activeCount: number;
  onApply: (filters: AdvancedFilter[], match: MatchMode) => void;
  onClear: () => void;
}) {
  const firstColumn = table.columns[0];
  const [open, setOpen] = useState(false);
  const [match, setMatch] = useState<MatchMode>('all');
  const [openSnapshot, setOpenSnapshot] = useState<{ conditions: DraftCondition[]; match: MatchMode } | null>(null);
  const [conditions, setConditions] = useState<DraftCondition[]>(() => firstColumn ? [createCondition(firstColumn)] : []);

  const columnMap = useMemo(() => new Map(table.columns.map(column => [column.field_key, column])), [table.columns]);

  function addCondition() {
    if (!firstColumn) return;
    setConditions(current => [...current, createCondition(firstColumn)]);
  }

  function changeColumn(id: string, fieldKey: string) {
    const column = columnMap.get(fieldKey);
    if (!column) return;
    setConditions(current => current.map(condition => condition.id === id ? createCondition(column) : condition));
  }

  function patch(id: string, values: Partial<DraftCondition>) {
    setConditions(current => current.map(condition => condition.id === id ? { ...condition, ...values } : condition));
  }

  function remove(id: string) {
    setConditions(current => current.filter(condition => condition.id !== id));
  }

  function closeAsCancel() {
    if (openSnapshot) {
      setConditions(openSnapshot.conditions.map(condition => ({ ...condition })));
      setMatch(openSnapshot.match);
    }
    setOpenSnapshot(null);
    setOpen(false);
  }

  function toggleOpen() {
    if (open) {
      closeAsCancel();
      return;
    }
    setOpenSnapshot({
      conditions: conditions.map(condition => ({ ...condition })),
      match,
    });
    setOpen(true);
  }

  function clear() {
    setConditions(firstColumn ? [createCondition(firstColumn)] : []);
    setMatch('all');
    setOpenSnapshot(null);
    onClear();
    setOpen(false);
  }

  function apply() {
    const filters: AdvancedFilter[] = conditions.map(({ id: _id, ...condition }) => {
      if (VALUELESS_OPERATORS.has(condition.operator)) {
        return { field_key: condition.field_key, operator: condition.operator };
      }
      if (condition.operator !== 'between') {
        return { field_key: condition.field_key, operator: condition.operator, value: condition.value };
      }
      return condition;
    });
    onApply(filters, match);
    setOpenSnapshot(null);
    setOpen(false);
  }

  return <div className="advanced-search">
    <button type="button" className={`button secondary advanced-toggle ${activeCount ? 'advanced-toggle-active' : ''}`} onClick={toggleOpen}>
      Advanced Search{activeCount ? ` (${activeCount})` : ''}
      <span aria-hidden>{open ? '▴' : '▾'}</span>
    </button>

    {open && <div className="advanced-panel">
      <div className="advanced-heading-row">
        <div>
          <div className="advanced-title">Advanced Search</div>
          <div className="muted advanced-help">Filter this table by one or more columns.</div>
        </div>
        <label className="advanced-match-label">
          Match
          <select className="select advanced-match" value={match} onChange={e => setMatch(e.target.value as MatchMode)}>
            <option value="all">all conditions</option>
            <option value="any">any condition</option>
          </select>
        </label>
      </div>

      <div className="advanced-condition-list">
        {conditions.map((condition, index) => {
          const column = columnMap.get(condition.field_key) || firstColumn;
          if (!column) return null;
          const operators = operatorsFor(column);
          const valueless = VALUELESS_OPERATORS.has(condition.operator);
          return <div className="advanced-condition" key={condition.id}>
            <div className="advanced-condition-number">{index + 1}</div>
            <select className="select" value={condition.field_key} onChange={e => changeColumn(condition.id, e.target.value)} aria-label={`Condition ${index + 1} column`}>
              {table.columns.map(candidate => <option key={candidate.id} value={candidate.field_key}>{candidate.name}</option>)}
            </select>
            <select className="select" value={condition.operator} onChange={e => patch(condition.id, { operator: e.target.value, value: defaultValueFor(column), value2: '' })} aria-label={`Condition ${index + 1} operator`}>
              {operators.map(operator => <option key={operator.value} value={operator.value}>{operator.label}</option>)}
            </select>
            <div className={`advanced-values ${condition.operator === 'between' ? 'advanced-values-between' : ''}`}>
              {!valueless && <FilterValue column={column} condition={condition} onChange={value => patch(condition.id, { value })}/>} 
              {condition.operator === 'between' && <>
                <span className="advanced-and">and</span>
                <FilterValue column={column} condition={condition} second onChange={value2 => patch(condition.id, { value2 })}/>
              </>}
              {valueless && <span className="advanced-no-value">No value required</span>}
            </div>
            <button type="button" className="advanced-remove" title="Remove condition" aria-label={`Remove condition ${index + 1}`} onClick={() => remove(condition.id)}>×</button>
          </div>;
        })}
      </div>

      <div className="advanced-actions">
        <button type="button" className="button secondary" onClick={addCondition}>+ Add condition</button>
        <span className="advanced-actions-spacer"/>
        <button type="button" className="button secondary" onClick={clear}>Clear</button>
        <button type="button" className="button secondary" onClick={closeAsCancel}>Cancel</button>
        <button type="button" className="button" onClick={apply} disabled={!conditions.length}>Apply Changes</button>
      </div>
    </div>}
  </div>;
}
