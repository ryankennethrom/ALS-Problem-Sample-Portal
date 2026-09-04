'use client';

import { useMemo, useState } from 'react';
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
