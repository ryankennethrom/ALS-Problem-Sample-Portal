'use client';

import { useMemo, useState } from 'react';
import {
  QueueAdvancedFilter,
  QueueFilterField,
  QueueMatchMode,
  WORKFLOW_QUEUE_FIELDS,
} from '@/lib/workflowQueueSearch';

type DraftFilter = QueueAdvancedFilter & { id: string };
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
const DATE_OPERATORS: Operator[] = [
  { value: 'equals', label: 'Is' },
  { value: 'not_equals', label: 'Is not' },
  { value: 'before', label: 'Is before' },
  { value: 'after', label: 'Is after' },
  { value: 'between', label: 'Is between' },
  { value: 'is_empty', label: 'Is empty' },
  { value: 'is_not_empty', label: 'Is not empty' },
];
const CHOICE_OPERATORS: Operator[] = [
  { value: 'equals', label: 'Is' },
  { value: 'not_equals', label: 'Is not' },
  { value: 'is_empty', label: 'Is empty' },
  { value: 'is_not_empty', label: 'Is not empty' },
];
const VALUELESS = new Set(['is_empty', 'is_not_empty']);

function operatorsFor(field: QueueFilterField) {
  if (field.type === 'number') return NUMBER_OPERATORS;
  if (field.type === 'datetime') return DATE_OPERATORS;
  if (field.type === 'choice') return CHOICE_OPERATORS;
  return TEXT_OPERATORS;
}

function makeId() {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
}

function makeFilter(field: QueueFilterField): DraftFilter {
  return { id: makeId(), field_key: field.key, operator: operatorsFor(field)[0].value, value: '', value2: '' };
}

export default function WorkflowQueueAdvancedSearch({
  activeCount,
  onApply,
  onClear,
}: {
  activeCount: number;
  onApply: (filters: QueueAdvancedFilter[], match: QueueMatchMode) => void;
  onClear: () => void;
}) {
  const firstField = WORKFLOW_QUEUE_FIELDS[0];
  const [open, setOpen] = useState(false);
  const [match, setMatch] = useState<QueueMatchMode>('all');
  const [conditions, setConditions] = useState<DraftFilter[]>([makeFilter(firstField)]);
  const [snapshot, setSnapshot] = useState<{ conditions: DraftFilter[]; match: QueueMatchMode } | null>(null);
  const fieldMap = useMemo(() => new Map(WORKFLOW_QUEUE_FIELDS.map(field => [field.key, field])), []);

  function toggle() {
    if (open) {
      if (snapshot) {
        setConditions(snapshot.conditions.map(condition => ({ ...condition })));
        setMatch(snapshot.match);
      }
      setOpen(false);
      setSnapshot(null);
      return;
    }
    setSnapshot({ conditions: conditions.map(condition => ({ ...condition })), match });
    setOpen(true);
  }

  function patch(id: string, values: Partial<DraftFilter>) {
    setConditions(current => current.map(condition => condition.id === id ? { ...condition, ...values } : condition));
  }

  function changeField(id: string, key: string) {
    const field = fieldMap.get(key);
    if (!field) return;
    setConditions(current => current.map(condition => condition.id === id ? makeFilter(field) : condition));
  }

  function apply() {
    const filters = conditions.map(({ id: _id, ...condition }) => {
      if (VALUELESS.has(condition.operator)) return { field_key: condition.field_key, operator: condition.operator };
      if (condition.operator !== 'between') return { field_key: condition.field_key, operator: condition.operator, value: condition.value };
      return condition;
    });
    onApply(filters, match);
    setSnapshot(null);
    setOpen(false);
  }

  function clear() {
    setConditions([makeFilter(firstField)]);
    setMatch('all');
    setSnapshot(null);
    onClear();
    setOpen(false);
  }

  return <div className="advanced-search">
    <button type="button" className={`button secondary advanced-toggle ${activeCount ? 'advanced-toggle-active' : ''}`} onClick={toggle}>
      Advanced Search{activeCount ? ` (${activeCount})` : ''}<span aria-hidden>{open ? '▴' : '▾'}</span>
    </button>
    {open && <div className="advanced-panel">
      <div className="advanced-heading-row">
        <div><div className="advanced-title">Advanced Search</div><div className="muted advanced-help">Filter this workflow queue by one or more fields.</div></div>
        <label className="advanced-match-label">Match
          <select className="select advanced-match" value={match} onChange={event => setMatch(event.target.value as QueueMatchMode)}>
            <option value="all">all conditions</option><option value="any">any condition</option>
          </select>
        </label>
      </div>
      <div className="advanced-condition-list">
        {conditions.map((condition, index) => {
          const field = fieldMap.get(condition.field_key) || firstField;
          const valueless = VALUELESS.has(condition.operator);
          return <div className="advanced-condition" key={condition.id}>
            <div className="advanced-condition-number">{index + 1}</div>
            <select className="select" value={condition.field_key} onChange={event => changeField(condition.id, event.target.value)}>
              {WORKFLOW_QUEUE_FIELDS.map(candidate => <option key={candidate.key} value={candidate.key}>{candidate.label}</option>)}
            </select>
            <select className="select" value={condition.operator} onChange={event => patch(condition.id, { operator: event.target.value, value: '', value2: '' })}>
              {operatorsFor(field).map(operator => <option key={operator.value} value={operator.value}>{operator.label}</option>)}
            </select>
            <div className={`advanced-values ${valueless ? 'advanced-values-empty' : ''} ${condition.operator === 'between' ? 'advanced-values-between' : ''}`}>
              {!valueless && (field.type === 'choice'
                ? <select className="select advanced-value" value={String(condition.value || '')} onChange={event => patch(condition.id, { value: event.target.value })}>
                    <option value="">Select a value…</option>{(field.choices || []).map(choice => <option key={choice} value={choice}>{choice}</option>)}
                  </select>
                : <input className="input advanced-value" type={field.type === 'number' ? 'number' : field.type === 'datetime' ? 'datetime-local' : 'text'} value={String(condition.value || '')} placeholder="Value" onChange={event => patch(condition.id, { value: event.target.value })} />)}
              {!valueless && condition.operator === 'between' && <>
                <span className="advanced-and">and</span>
                <input className="input advanced-value" type={field.type === 'number' ? 'number' : field.type === 'datetime' ? 'datetime-local' : 'text'} value={String(condition.value2 || '')} placeholder="Second value" onChange={event => patch(condition.id, { value2: event.target.value })} />
              </>}
              {valueless && <span className="advanced-no-value">No value required</span>}
            </div>
            <button type="button" className="advanced-remove" aria-label={`Remove condition ${index + 1}`} onClick={() => setConditions(current => current.filter(item => item.id !== condition.id))}>×</button>
          </div>;
        })}
      </div>
      <div className="advanced-actions">
        <button type="button" className="button secondary" onClick={() => setConditions(current => [...current, makeFilter(firstField)])}>+ Add condition</button>
        <span className="advanced-actions-spacer" />
        <button type="button" className="button secondary" onClick={clear}>Clear</button>
        <button type="button" className="button secondary" onClick={toggle}>Cancel</button>
        <button type="button" className="button" onClick={apply}>Apply</button>
      </div>
    </div>}
  </div>;
}
