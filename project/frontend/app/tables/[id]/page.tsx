'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { queueToastForReload } from '@/lib/toast';
import { COLUMN_TYPES, ColumnType, GroupRole, GroupUser, IntercolumnRule, IntercolumnRuleDirection, ProblemColumn, ProblemTable } from '@/lib/problemTables';
import DistributorAutocomplete from '@/components/DistributorAutocomplete';
import EndUserAutocomplete from '@/components/EndUserAutocomplete';
import ClientEmailAutocomplete from '@/components/ClientEmailAutocomplete';
import BrandAutocomplete from '@/components/BrandAutocomplete';

const CURRENT_WORKFLOWS = [
  'CS Follow-Up',
  'Waiting for Customer Response',
  'To be Disposed',
  'To be shipped back to client',
  'To be back to testing',
  'Back to testing',
  'Disposed',
  'Shipped back to client',
] as const;

function blankDefault(type: ColumnType): unknown {
  if (type === 'multi_choice' || type === 'client_email') return [];
  if (type === 'boolean') return null;
  return '';
}

function normalizeDefault(type: ColumnType, value: unknown): unknown {
  if (type === 'multi_choice' || type === 'client_email') return Array.isArray(value) && value.length ? value : null;
  if (type === 'boolean') return value === true || value === false ? value : null;
  return value === '' || value === undefined ? null : value;
}

function DefaultValueField({
  type,
  choices,
  value,
  onChange,
  idSuffix = 'new',
  groupRole = 'lab_technician',
  dependencyConfigured = false,
}: {
  type: ColumnType;
  choices: string[];
  value: unknown;
  onChange: (value: unknown) => void;
  idSuffix?: string;
  groupRole?: GroupRole;
  dependencyConfigured?: boolean;
}) {
  const id = `default-${idSuffix}`;
  if (type === 'row_creator' || type === 'recent_row_modifier' || type === 'date_today') return null;
  const [groupUsers, setGroupUsers] = useState<GroupUser[]>([]);

  useEffect(() => {
    if (type !== 'group') { setGroupUsers([]); return; }
    api(`/auth/users/?role=${encodeURIComponent(groupRole)}`)
      .then(data => setGroupUsers(Array.isArray(data) ? data : []))
      .catch(() => setGroupUsers([]));
  }, [type, groupRole]);

  if (type === 'distributor') {
    return <DistributorAutocomplete id={id} label="Default value" value={value} onChange={onChange as (value: string) => void} placeholder="Optional default distributor…" />;
  }
  if (type === 'brand') {
    return <BrandAutocomplete id={id} label="Default value" value={value} onChange={onChange as (value: string) => void} placeholder="Optional default brand…" />;
  }
  if (type === 'end_user') {
    return <EndUserAutocomplete id={id} label="Default value" value={value} onChange={onChange as (value: string) => void} placeholder="Optional default end user…" />;
  }

  if (type === 'client_email') {
    if (dependencyConfigured) return null;
    return <ClientEmailAutocomplete id={id} label="Default value" value={value} onChange={onChange as (value: string[]) => void} placeholder="Fuzzy-search default client emails…" />;
  }

  if (type === 'fixed') {
    return <div className="field"><label htmlFor={id}>Fixed value <span className="required-marker" aria-hidden="true">*</span></label><input id={id} className="input" value={String(value ?? '')} onChange={e => onChange(e.target.value)} required placeholder="Value shown in every row" /></div>;
  }

  if (type === 'long_text') {
    return <div className="field"><label htmlFor={id}>Default value</label><textarea id={id} className="textarea" value={String(value ?? '')} onChange={e => onChange(e.target.value)} placeholder="Optional" /></div>;
  }

  if (type === 'choice') {
    return <div className="field"><label htmlFor={id}>Default value</label><select id={id} className="select" value={String(value ?? '')} onChange={e => onChange(e.target.value)}><option value="">-- No default --</option>{choices.map(choice => <option key={choice} value={choice}>{choice}</option>)}</select></div>;
  }

  if (type === 'multi_choice') {
    const selected = Array.isArray(value) ? value.map(String) : [];
    return <fieldset className="field choice-fieldset"><legend>Default value</legend><div className="choice-list">{choices.length === 0 && <span className="muted">Add choices above first.</span>}{choices.map(choice => <label className="check-label" key={choice}><input type="checkbox" checked={selected.includes(choice)} onChange={e => onChange(e.target.checked ? [...selected, choice] : selected.filter(item => item !== choice))} /><span>{choice}</span></label>)}</div></fieldset>;
  }

  if (type === 'group') {
    const current = value == null ? '' : String(value);
    return <div className="field"><label htmlFor={id}>Default value</label><select id={id} className="select" value={current} onChange={e => onChange(e.target.value)}><option value="">-- No default --</option>{groupUsers.map(user => <option key={user.id} value={user.email}>{user.name && user.name.toLowerCase() !== user.email.toLowerCase() ? `${user.name} (${user.email})` : user.email}</option>)}</select></div>;
  }

  if (type === 'boolean') {
    const current = value === true ? 'true' : value === false ? 'false' : '';
    return <div className="field"><label htmlFor={id}>Default value</label><select id={id} className="select" value={current} onChange={e => onChange(e.target.value === '' ? null : e.target.value === 'true')}><option value="">-- No default --</option><option value="true">Yes</option><option value="false">No</option></select></div>;
  }

  const inputType = type === 'number' ? 'number'
    : (type === 'date' || type === 'date_today') ? 'date'
    : type === 'datetime' ? 'datetime-local'
    : type === 'time' ? 'time'
    : type === 'email' ? 'email'
    : type === 'phone' ? 'tel'
    : type === 'url' ? 'url'
    : 'text';

  return <div className="field"><label htmlFor={id}>Default value</label><input id={id} className="input" type={inputType} step={type === 'number' ? 'any' : undefined} value={value == null ? '' : String(value)} onChange={e => onChange(e.target.value)} placeholder={['text', 'email', 'phone', 'url'].includes(type) ? 'Optional' : undefined} /></div>;
}

function ClientEmailDependencyPriority({
  value,
  onChange,
  columns,
  excludeId,
}: {
  value: string[];
  onChange: (value: string[]) => void;
  columns: ProblemColumn[];
  excludeId?: string;
}) {
  const candidates = columns.filter(candidate => !candidate.is_system && candidate.id !== excludeId && ['distributor', 'end_user', 'text', 'fixed'].includes(candidate.column_type));

  function addDependency() {
    const next = candidates.find(candidate => !value.includes(candidate.id));
    if (next) onChange([...value, next.id]);
  }

  function replaceAt(index: number, id: string) {
    const next = [...value];
    next[index] = id;
    onChange(next.filter((item, position) => next.indexOf(item) === position));
  }

  function move(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= value.length) return;
    const next = [...value];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  }

  return <div className="field client-email-dependency-field">
    <label>Client Email dependency priority <span className="muted">(optional)</span></label>
    <div className="stack client-email-dependency-stack">
      {value.map((dependencyId, index) => <div className="client-email-dependency-row" key={`${dependencyId}-${index}`}>
        <span className="client-email-priority-label">Priority {index + 1}</span>
        <select className="select client-email-dependency-select" value={dependencyId} onChange={e => replaceAt(index, e.target.value)}>
          {candidates.map(candidate => <option key={candidate.id} value={candidate.id} disabled={value.includes(candidate.id) && candidate.id !== dependencyId}>{candidate.name} ({candidate.column_type_label})</option>)}
        </select>
        <button type="button" className="button secondary client-email-priority-button" onClick={() => move(index, -1)} disabled={index === 0} title="Move up">↑</button>
        <button type="button" className="button secondary client-email-priority-button" onClick={() => move(index, 1)} disabled={index === value.length - 1} title="Move down">↓</button>
        <button type="button" className="button danger client-email-remove-button" onClick={() => onChange(value.filter((_, position) => position !== index))}>Remove</button>
      </div>)}
      {value.length === 0 && <div className="muted result-meta client-email-dependency-help">No dependency: fuzzy-search all imported client emails.</div>}
      {value.length > 0 && <div className="muted result-meta client-email-dependency-help">Dependencies are checked from top to bottom. The first populated company field with at least one imported email becomes the source. If it has no emails, the next field is tried. Dependent Client Email columns do not use a table-wide default.</div>}
      {value.length < candidates.length && <div><button type="button" className="button secondary" onClick={addDependency}>+ Add fallback field</button></div>}
    </div>
  </div>;
}


const INTERCOLUMN_EDITABLE_SYSTEM_KEYS = new Set(['current-workflow', 'dispose-automatically']);
const INTERCOLUMN_OTHER_TYPES = new Set<ColumnType>([
  'text', 'long_text', 'number', 'choice', 'date', 'date_today', 'datetime', 'time',
  'boolean', 'email', 'phone', 'url', 'intercolumn_controller',
]);

function isIntercolumnCandidate(column: ProblemColumn, excludeId?: string) {
  if (excludeId && column.id === excludeId) return false;
  if (column.is_system) return INTERCOLUMN_EDITABLE_SYSTEM_KEYS.has(column.field_key);
  return INTERCOLUMN_OTHER_TYPES.has(column.column_type);
}

function emptyRuleValue(column?: ProblemColumn): unknown {
  return column?.column_type === 'boolean' ? null : '';
}

function RuleValueInput({ column, label, value, onChange, id }: { column: ProblemColumn; label: string; value: unknown; onChange: (value: unknown) => void; id: string }) {
  if (column.column_type === 'choice') {
    return <div className="field"><label htmlFor={id}>{label}</label><select id={id} className="select" value={value == null ? '' : String(value)} onChange={e => onChange(e.target.value)}><option value="">-- Choose value --</option>{(column.choices || []).map(choice => <option value={choice} key={choice}>{choice}</option>)}</select></div>;
  }
  if (column.column_type === 'boolean') {
    const current = value === true ? 'true' : value === false ? 'false' : '';
    return <div className="field"><label htmlFor={id}>{label}</label><select id={id} className="select" value={current} onChange={e => onChange(e.target.value === '' ? null : e.target.value === 'true')}><option value="">-- Choose value --</option><option value="true">Yes</option><option value="false">No</option></select></div>;
  }
  if (column.column_type === 'long_text') {
    return <div className="field"><label htmlFor={id}>{label}</label><textarea id={id} className="textarea compact-textarea" value={value == null ? '' : String(value)} onChange={e => onChange(e.target.value)} /></div>;
  }
  const inputType = column.column_type === 'number' ? 'number'
    : (column.column_type === 'date' || column.column_type === 'date_today') ? 'date'
    : column.column_type === 'datetime' ? 'datetime-local'
    : column.column_type === 'time' ? 'time'
    : column.column_type === 'email' ? 'email'
    : column.column_type === 'phone' ? 'tel'
    : column.column_type === 'url' ? 'url'
    : 'text';
  return <div className="field"><label htmlFor={id}>{label}</label><input id={id} className="input" type={inputType} step={column.column_type === 'number' ? 'any' : undefined} value={value == null ? '' : String(value)} onChange={e => onChange(e.target.value)} /></div>;
}

function IntercolumnRulesEditor({
  rules,
  onChange,
  columns,
  controllerName,
  excludeId,
  idPrefix,
}: {
  rules: IntercolumnRule[];
  onChange: (rules: IntercolumnRule[]) => void;
  columns: ProblemColumn[];
  controllerName: string;
  excludeId?: string;
  idPrefix: string;
}) {
  const candidates = columns.filter(column => isIntercolumnCandidate(column, excludeId));

  function addRule() {
    const other = candidates[0];
    if (!other) return;
    onChange([...rules, {
      other_column_id: other.id,
      direction: 'other_to_controller',
      when_other_equals: emptyRuleValue(other),
      set_controller_to: '',
      when_controller_equals: '',
      set_other_to: emptyRuleValue(other),
    }]);
  }

  function updateRule(index: number, patch: Partial<IntercolumnRule>) {
    onChange(rules.map((rule, position) => position === index ? { ...rule, ...patch } : rule));
  }

  function changeOther(index: number, otherId: string) {
    const other = candidates.find(candidate => candidate.id === otherId);
    updateRule(index, {
      other_column_id: otherId,
      when_other_equals: emptyRuleValue(other),
      set_other_to: emptyRuleValue(other),
    });
  }

  return <div className="field intercolumn-rules-field">
    <label>Intercolumn rules</label>
    <div className="stack">
      {rules.map((rule, index) => {
        const other = candidates.find(candidate => candidate.id === rule.other_column_id) || candidates[0];
        if (!other) return null;
        const controllerLabel = controllerName.trim() || 'this controller';
        return <div className="intercolumn-rule-card" key={`${idPrefix}-${index}`}>
          <div className="intercolumn-rule-header"><strong>Rule {index + 1}</strong><button type="button" className="button danger" onClick={() => onChange(rules.filter((_, position) => position !== index))}>Remove</button></div>
          <div className="intercolumn-rule-grid">
            <div className="field"><label>Other field</label><select className="select" value={other.id} onChange={e => changeOther(index, e.target.value)}>{candidates.map(candidate => <option value={candidate.id} key={candidate.id}>{candidate.name} ({candidate.column_type_label})</option>)}</select></div>
            <div className="field"><label>Direction</label><select className="select" value={rule.direction} onChange={e => updateRule(index, { direction: e.target.value as IntercolumnRuleDirection })}><option value="other_to_controller">Other field → Controller</option><option value="controller_to_other">Controller → Other field</option><option value="both">Both directions</option></select></div>
          </div>
          {(rule.direction === 'other_to_controller' || rule.direction === 'both') && <div className="intercolumn-condition-row">
            <RuleValueInput column={other} label={`If ${other.name} equals`} value={rule.when_other_equals} onChange={value => updateRule(index, { when_other_equals: value })} id={`${idPrefix}-${index}-other-trigger`} />
            <div className="field"><label htmlFor={`${idPrefix}-${index}-controller-result`}>Set {controllerLabel} to</label><input id={`${idPrefix}-${index}-controller-result`} className="input" value={rule.set_controller_to ?? ''} onChange={e => updateRule(index, { set_controller_to: e.target.value })} /></div>
          </div>}
          {(rule.direction === 'controller_to_other' || rule.direction === 'both') && <div className="intercolumn-condition-row">
            <div className="field"><label htmlFor={`${idPrefix}-${index}-controller-trigger`}>If {controllerLabel} equals</label><input id={`${idPrefix}-${index}-controller-trigger`} className="input" value={rule.when_controller_equals ?? ''} onChange={e => updateRule(index, { when_controller_equals: e.target.value })} /></div>
            <RuleValueInput column={other} label={`Set ${other.name} to`} value={rule.set_other_to} onChange={value => updateRule(index, { set_other_to: value })} id={`${idPrefix}-${index}-other-result`} />
          </div>}
        </div>;
      })}
      {rules.length === 0 && <div className="muted result-meta">No rules yet. Add a rule to connect this controller to another single-value field.</div>}
      {candidates.length > 0 ? <div><button type="button" className="button secondary" onClick={addRule}>+ Add Rule</button></div> : <div className="muted result-meta">Add another supported field before creating a controller rule.</div>}
      <div className="muted result-meta">Rules use exact equality. Both-direction rules are allowed. The backend repeatedly applies chained rules until values stabilize and rejects non-converging cycles.</div>
    </div>
  </div>;
}

function ColumnEditor({ column, allColumns, onChanged }: {column: ProblemColumn; allColumns: ProblemColumn[]; onChanged: () => Promise<void>}) {
  const [name, setName] = useState(column.name);
  const [columnDescription, setColumnDescription] = useState(column.description || '');
  const [type, setType] = useState<ColumnType>(column.column_type);
  const [choices, setChoices] = useState(column.choices.join('\n'));
  const [defaultValue, setDefaultValue] = useState<unknown>(column.default_value);
  const [groupRole, setGroupRole] = useState<GroupRole>((column.group_role || 'lab_technician') as GroupRole);
  const [dependencyIds, setDependencyIds] = useState<string[]>(column.client_email_dependencies || (column.depends_on_column ? [column.depends_on_column] : []));
  const [intercolumnRules, setIntercolumnRules] = useState<IntercolumnRule[]>(column.intercolumn_rules || []);
  const [required, setRequired] = useState(column.required);
  const [searchable, setSearchable] = useState(column.searchable);
  const [includeInCustomerNotification, setIncludeInCustomerNotification] = useState(column.include_in_customer_notification);
  const [busy, setBusy] = useState(false);

  if (column.is_system) {
    return <div className="column-editor system-column-editor">
      <div className="column-editor-grid">
        <div className="field"><label>Name</label><input className="input" value={column.name} disabled /></div>
        <div className="field"><label>Type</label><input className="input" value={column.field_key === 'problem-id' ? 'Auto-incrementing number' : 'Built-in'} disabled /></div>
        <div className="column-flags"><span className="badge blue">Built-in</span><span className="muted">{column.required ? 'Required · ' : ''}{column.searchable ? 'Searchable · ' : ''}cannot be edited or deleted</span></div>
      </div>
    </div>;
  }

  const choiceList = choices.split('\n').map(x => x.trim()).filter(Boolean);

  async function save() {
    setBusy(true);
    try {
      await api(`/problem-columns/${column.id}/`, {method:'PATCH', body:JSON.stringify({
        name,
        description: columnDescription,
        column_type:type,
        required: type === 'fixed' ? true : (type === 'row_creator' || type === 'recent_row_modifier') ? false : required,
        searchable,
        include_in_customer_notification: includeInCustomerNotification,
        choices: choiceList,
        group_role: type === 'group' ? groupRole : '',
        client_email_dependencies: type === 'client_email' ? dependencyIds : [],
        intercolumn_rules: type === 'intercolumn_controller' ? intercolumnRules : [],
        default_value: (type === 'row_creator' || type === 'recent_row_modifier' || type === 'date_today') ? null : (type === 'client_email' && dependencyIds.length ? null : normalizeDefault(type, defaultValue)),
      }), successMessage:'Column updated successfully.', errorMessage:'Could not update column'});
      await onChanged();
    } finally { setBusy(false); }
  }

  async function remove() {
    if (!confirm(`Delete column "${column.name}"? Existing values in this column will also be removed.`)) return;
    setBusy(true);
    try { await api(`/problem-columns/${column.id}/`, {method:'DELETE', successMessage:'Column deleted successfully.', errorMessage:'Could not delete column'}); await onChanged(); }
    finally { setBusy(false); }
  }

  function changeType(next: ColumnType) {
    setType(next);
    setDefaultValue(blankDefault(next));
    setRequired(next === 'fixed');
    if (next === 'group') setGroupRole('lab_technician');
    setDependencyIds([]);
    if (next !== 'intercolumn_controller') setIntercolumnRules([]);
  }

  return <div className="column-editor">
    <div className="column-editor-grid">
      <div className="field"><label>Name</label><input className="input" value={name} onChange={e=>setName(e.target.value)}/></div>
      <div className="field"><label>Type</label><select className="select" value={type} onChange={e=>changeType(e.target.value as ColumnType)}>{COLUMN_TYPES.map(t=><option key={t.value} value={t.value}>{t.label}</option>)}</select></div>
      <div className="field column-description-field"><label>Explanation <span className="muted">(optional)</span></label><textarea className="textarea compact-textarea" value={columnDescription} onChange={e=>setColumnDescription(e.target.value)} placeholder="Explain what this column is for or what users should enter. An (i) icon appears anywhere the column is shown." /></div>
      {(type === 'choice' || type === 'multi_choice') && <div className="field column-choice-options"><label>Choices (one per line)</label><textarea className="textarea compact-textarea" value={choices} onChange={e=>setChoices(e.target.value)}/></div>}
      {type === 'group' && <div className="field"><label>Group <span className="required-marker" aria-hidden="true"> *</span></label><select className="select" value={groupRole} onChange={e=>{ setGroupRole(e.target.value as GroupRole); setDefaultValue(''); }}><option value="lab_technician">Lab</option><option value="customer_service">Customer Service</option></select></div>}
      {type === 'client_email' && <ClientEmailDependencyPriority value={dependencyIds} onChange={next => { setDependencyIds(next); setDefaultValue(''); }} columns={allColumns} excludeId={column.id} />}
      {type === 'intercolumn_controller' && <IntercolumnRulesEditor rules={intercolumnRules} onChange={setIntercolumnRules} columns={allColumns} controllerName={name} excludeId={column.id} idPrefix={`controller-${column.id}`} />}
      <DefaultValueField type={type} choices={choiceList} value={defaultValue} onChange={setDefaultValue} idSuffix={column.id} groupRole={groupRole} dependencyConfigured={type === 'client_email' && dependencyIds.length > 0} />
      <div className="column-flags"><label className="check-label"><input type="checkbox" checked={type === 'fixed' ? true : (type === 'row_creator' || type === 'recent_row_modifier') ? false : required} disabled={type === 'fixed' || type === 'row_creator' || type === 'recent_row_modifier'} onChange={e=>setRequired(e.target.checked)}/> Required</label><label className="check-label"><input type="checkbox" checked={searchable} onChange={e=>setSearchable(e.target.checked)}/> Include in search</label><label className="check-label"><input type="checkbox" checked={includeInCustomerNotification} onChange={e=>setIncludeInCustomerNotification(e.target.checked)}/> Include in customer notification</label></div>
    </div>
    <div className="muted result-meta" style={{marginTop:6}}>{type === 'fixed' ? 'This value is read-only on rows. Changing it here updates every existing row in this table.' : type === 'row_creator' ? 'Read-only on rows. The server stores the email of the user who originally created each row, and that value cannot be changed later.' : type === 'recent_row_modifier' ? 'Read-only on rows. The server shows the staff email/username that most recently saved the row, or Customer when the latest change came from the public tracking link.' : type === 'date_today' ? 'Editable like a normal Date field. New tickets start with the current date automatically; changing this column setting does not overwrite existing valid dates.' : type === 'intercolumn_controller' ? 'This field stores a normal text value and can automatically set or be set by another supported field according to the rules above.' : type === 'group' ? 'Each row can select one user who currently belongs to the configured group.' : type === 'distributor' ? 'Each row uses fuzzy autocomplete against companies whose CoyType is Distributor.' : type === 'end_user' ? 'Each row uses fuzzy autocomplete against companies whose CoyType is End User.' : type === 'brand' ? 'Each row uses fuzzy autocomplete against distinct Brand values in the current Customer Export.' : type === 'client_email' ? (dependencyIds.length ? 'The row loads the active dependency company’s emails into a selectable list. Users can keep/delete selected addresses, clear all, add an email, and fuzzy-filter the list.' : 'Client Email is a multi-address list. Without dependencies, fuzzy search can discover imported emails and Keep Selected stores the chosen addresses.') : 'The default is used for newly created rows. Changing it here does not overwrite existing row values.'}</div>
    <div className="column-actions"><button className="button secondary" onClick={save} disabled={busy}>Save</button><button className="button danger" onClick={remove} disabled={busy}>Delete</button></div>
  </div>;
}

export default function TableSettings() {
  const { id } = useParams<{id:string}>();
  const router = useRouter();
  const [table, setTable] = useState<ProblemTable | null>(null);
  const [error, setError] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [ptDays, setPtDays] = useState(30);
  const [colName, setColName] = useState('');
  const [colDescription, setColDescription] = useState('');
  const [colType, setColType] = useState<ColumnType>('text');
  const [choices, setChoices] = useState('');
  const [defaultValue, setDefaultValue] = useState<unknown>('');
  const [colGroupRole, setColGroupRole] = useState<GroupRole>('lab_technician');
  const [colDependencyIds, setColDependencyIds] = useState<string[]>([]);
  const [colIntercolumnRules, setColIntercolumnRules] = useState<IntercolumnRule[]>([]);
  const [required, setRequired] = useState(false);
  const [searchable, setSearchable] = useState(true);
  const [includeInCustomerNotification, setIncludeInCustomerNotification] = useState(false);
  const [columnOrder, setColumnOrder] = useState<string[]>([]);
  const [savingColumnOrder, setSavingColumnOrder] = useState(false);

  async function load() {
    const d: ProblemTable = await api(`/problem-tables/${id}/`);
    setTable(d); setName(d.name); setDescription(d.description || ''); setPtDays(d.pt_days ?? 30);
    setColumnOrder(d.columns.map(column => column.id));
  }
  useEffect(() => { load().catch(e=>setError(e instanceof Error ? e.message : 'Failed')); }, [id]);

  async function saveTable(e: React.FormEvent) {
    e.preventDefault();
    await api(`/problem-tables/${id}/`, {method:'PATCH', body:JSON.stringify({name, description, pt_days: ptDays}), errorMessage:'Could not save table details'});
    queueToastForReload('success', 'Table details saved successfully.');
    window.location.reload();
  }

  async function addColumn(e: React.FormEvent) {
    e.preventDefault(); setError('');
    const choiceList = choices.split('\n').map(x=>x.trim()).filter(Boolean);
    try {
      await api('/problem-columns/', {method:'POST', body:JSON.stringify({
        table:id,
        name:colName,
        description: colDescription,
        column_type:colType,
        required: colType === 'fixed' ? true : (colType === 'row_creator' || colType === 'recent_row_modifier') ? false : required,
        searchable,
        include_in_customer_notification: includeInCustomerNotification,
        choices:choiceList,
        group_role: colType === 'group' ? colGroupRole : '',
        client_email_dependencies: colType === 'client_email' ? colDependencyIds : [],
        intercolumn_rules: colType === 'intercolumn_controller' ? colIntercolumnRules : [],
        default_value: (colType === 'row_creator' || colType === 'recent_row_modifier' || colType === 'date_today') ? null : (colType === 'client_email' && colDependencyIds.length ? null : normalizeDefault(colType, defaultValue)),
      }), successMessage:'Column added successfully.', errorMessage:'Could not add column'});
      setColName('');
      setColDescription('');
      setColType('text');
      setChoices('');
      setDefaultValue('');
      setColGroupRole('lab_technician');
      setColDependencyIds([]);
      setColIntercolumnRules([]);
      setRequired(false);
      setSearchable(true);
      setIncludeInCustomerNotification(false);
      await load();
    } catch(e) { setError(e instanceof Error ? e.message : 'Failed to add column'); }
  }

  function moveColumn(columnId: string, direction: -1 | 1) {
    setColumnOrder(current => {
      const index = current.indexOf(columnId);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  async function saveColumnOrder() {
    if (!table || savingColumnOrder) return;
    setSavingColumnOrder(true);
    setError('');
    try {
      const updated: ProblemTable = await api(`/problem-tables/${id}/reorder-columns/`, {
        method: 'POST',
        body: JSON.stringify({ column_ids: columnOrder }),
        successMessage: 'Field order saved successfully.',
        errorMessage: 'Could not save field order',
      });
      setTable(updated);
      setColumnOrder(updated.columns.map(column => column.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save field order');
    } finally {
      setSavingColumnOrder(false);
    }
  }

  async function deleteTable() {
    if (!table || !confirm(`Delete table "${table.name}"? Only empty non-default tables can be deleted.`)) return;
    try { await api(`/problem-tables/${id}/`, {method:'DELETE', successMessage:'Ticket table deleted successfully.', errorMessage:'Could not delete ticket table'}); router.push('/tables'); }
    catch(e) { setError(e instanceof Error ? e.message : 'Could not delete table'); }
  }

  function changeNewColumnType(next: ColumnType) {
    setColType(next);
    setDefaultValue(blankDefault(next));
    setRequired(next === 'fixed');
    if (next === 'group') setColGroupRole('lab_technician');
    setColDependencyIds([]);
    if (next !== 'intercolumn_controller') setColIntercolumnRules([]);
  }

  if (!table) return <div>{error || 'Loading…'}</div>;
  const newChoiceList = choices.split('\n').map(x=>x.trim()).filter(Boolean);

  return <div>
    <div className="page-toolbar">
      <div><div className="eyebrow">Table settings</div><h1 className="page-heading" style={{marginBottom:0}}>{table.name}</h1></div>
      <div className="toolbar-actions"><Link className="button secondary" href={`/problem-samples?table=${table.id}`}>Open Table</Link>{!table.is_default && <button className="button danger" onClick={deleteTable}>Delete Table</button>}</div>
    </div>

    {error && <div className="card error" style={{marginBottom:14}}>{error}</div>}

    <div className="two-col table-settings-layout">
      <div className="stack">
        <section className="panel panel-blue">
          <div className="panel-header">Field order</div>
          <div className="panel-body stack">
            <div className="muted result-meta">Move fields earlier or later to control their left-to-right order in this table. The same order is also used when ticket fields are shown in forms and details.</div>
            <div className="field-order-list">
              {columnOrder.map((columnId, index) => {
                const column = table.columns.find(candidate => candidate.id === columnId);
                if (!column) return null;
                return <div className="field-order-row" key={column.id}>
                  <div className="field-order-index">{index + 1}</div>
                  <div className="field-order-label"><strong>{column.name}</strong><span>{column.is_system ? 'Built-in' : column.column_type_label}</span></div>
                  <div className="field-order-actions">
                    <button type="button" className="button secondary" onClick={() => moveColumn(column.id, -1)} disabled={index === 0 || savingColumnOrder} aria-label={`Move ${column.name} earlier`}>↑ Earlier</button>
                    <button type="button" className="button secondary" onClick={() => moveColumn(column.id, 1)} disabled={index === columnOrder.length - 1 || savingColumnOrder} aria-label={`Move ${column.name} later`}>↓ Later</button>
                  </div>
                </div>;
              })}
            </div>
            <div><button type="button" className="button" onClick={saveColumnOrder} disabled={savingColumnOrder}>{savingColumnOrder ? 'Saving…' : 'Save field order'}</button></div>
          </div>
        </section>
        <section className="panel panel-blue">
          <div className="panel-header">Columns ({table.columns.length})</div>
          <div className="panel-body stack">
            {table.columns.map(c => <ColumnEditor key={c.id} column={c} allColumns={table.columns} onChanged={load}/>)}
          </div>
        </section>
        <section className="panel">
          <div className="panel-header">Table Details</div>
          <form className="panel-body stack" onSubmit={saveTable}>
            <div className="field"><label>Name</label><input className="input" value={name} onChange={e=>setName(e.target.value)} required/></div>
            <div className="field"><label>Description</label><textarea className="textarea" value={description} onChange={e=>setDescription(e.target.value)}/></div>
            <div className="field"><label>Ticket Expiration Period (days)</label><input className="input" type="number" min={0} max={3650} value={ptDays} onChange={e=>{ const value = Number(e.target.value); setPtDays(Number.isFinite(value) ? Math.min(3650, Math.max(0, value)) : 0); }} required/><div className="muted result-meta">Each time Dispose Automatically changes from No to Yes, a new expiration period of this many days starts. When it ends, Current Workflow automatically changes to To be Disposed. Enter 0 for an immediate transition.</div></div>
            <div className="muted result-meta">Ticket Tracking Links remain available for 30 days after the most recent change to a routed disposal, shipping, or back-to-testing Current Workflow. Returning Current Workflow to CS Follow-Up clears that expiry clock and makes the tracking link accessible again.</div>
            <div><button className="button">Save Table Details</button></div>
          </form>
        </section>
        <section className="panel">
          <div className="panel-header">Current Workflow</div>
          <div className="panel-body stack">
            <div className="muted result-meta">Current Workflow is the required built-in routing field. These values are fixed because the system uses them for CS Follow-Up, disposal, shipping, back-to-testing, and customer tracking:</div>
            <div className="status-settings-list">
              {CURRENT_WORKFLOWS.map(label => <div className="status-settings-row" key={label}><input className="input" value={label} disabled readOnly/><span className="badge blue">Workflow</span></div>)}
            </div>
          </div>
        </section>
      </div>

      <aside className="panel add-column-panel">
        <div className="panel-header">Add Column</div>
        <div className="panel-body stack">
          <form className="stack" onSubmit={addColumn}>
            <div className="field"><label>Column name</label><input className="input" value={colName} onChange={e=>setColName(e.target.value)} required placeholder="e.g. Priority"/></div>
            <div className="field"><label>Explanation <span className="muted">(optional)</span></label><textarea className="textarea compact-textarea" value={colDescription} onChange={e=>setColDescription(e.target.value)} placeholder="Explain what this column means. Leave blank to hide the (i) icon." /></div>
            <div className="field"><label>Column type</label><select className="select" value={colType} onChange={e=>changeNewColumnType(e.target.value as ColumnType)}>{COLUMN_TYPES.map(t=><option key={t.value} value={t.value}>{t.label}</option>)}</select></div>
            {(colType === 'choice' || colType === 'multi_choice') && <div className="field"><label>Choices (one per line)</label><textarea className="textarea" value={choices} onChange={e=>setChoices(e.target.value)} placeholder={'New\nIn progress\nResolved'}/></div>}
            {colType === 'group' && <div className="field"><label>Group <span className="required-marker" aria-hidden="true"> *</span></label><select className="select" value={colGroupRole} onChange={e=>{ setColGroupRole(e.target.value as GroupRole); setDefaultValue(''); }}><option value="lab_technician">Lab</option><option value="customer_service">Customer Service</option></select></div>}
            {colType === 'client_email' && <ClientEmailDependencyPriority value={colDependencyIds} onChange={next => { setColDependencyIds(next); setDefaultValue(''); }} columns={table.columns} />}
            {colType === 'intercolumn_controller' && <IntercolumnRulesEditor rules={colIntercolumnRules} onChange={setColIntercolumnRules} columns={table.columns} controllerName={colName} idPrefix="controller-new" />}
            <DefaultValueField type={colType} choices={newChoiceList} value={defaultValue} onChange={setDefaultValue} groupRole={colGroupRole} dependencyConfigured={colType === 'client_email' && colDependencyIds.length > 0} />
            <div className="muted result-meta">{colType === 'fixed' ? 'The fixed value is applied to every existing row and every future row, and cannot be edited from a ticket.' : colType === 'row_creator' ? 'The value is filled automatically with the email of the user who created each row. Existing rows are backfilled from their recorded creator, and users cannot edit this field.' : colType === 'recent_row_modifier' ? 'The value is filled automatically with the staff email/username that most recently saved the row, or Customer when the latest change came from the public tracking link. Existing rows are backfilled from their recorded modifier, and users cannot edit this field.' : colType === 'date_today' ? 'Existing rows are filled with today when the column is added. Every new ticket starts with that day’s current date, and staff can edit the date afterward.' : colType === 'intercolumn_controller' ? 'This field stores a normal text value. Add one or more rules to synchronize it with another supported field in either direction or both.' : colType === 'group' ? 'Choose which employee group this column draws from. Row values are users registered in that group.' : colType === 'distributor' ? 'Row values use fuzzy company-name suggestions restricted to CoyType = Distributor.' : colType === 'end_user' ? 'Row values use fuzzy company-name suggestions restricted to CoyType = End User.' : colType === 'brand' ? 'Row values use fuzzy suggestions from distinct Brand values in the current Customer Export.' : colType === 'client_email' ? (colDependencyIds.length ? 'Dependencies are checked from highest to lowest priority. The first company with imported emails seeds a multi-email list that users can keep, remove, clear, or extend manually.' : 'Without dependencies, users can fuzzy-search the imported customer directory and keep multiple email addresses.') : 'When the column is added, this value fills the column for existing rows and pre-fills it for future tickets.'}</div>
            <label className="check-label"><input type="checkbox" checked={colType === 'fixed' ? true : (colType === 'row_creator' || colType === 'recent_row_modifier') ? false : required} disabled={colType === 'fixed' || colType === 'row_creator' || colType === 'recent_row_modifier'} onChange={e=>setRequired(e.target.checked)}/> Required value</label>
            <label className="check-label"><input type="checkbox" checked={searchable} onChange={e=>setSearchable(e.target.checked)}/> Include this column in fuzzy search</label>
            <label className="check-label"><input type="checkbox" checked={includeInCustomerNotification} onChange={e=>setIncludeInCustomerNotification(e.target.checked)}/> Include in customer notification</label>
            <div className="muted result-meta">Supported types: text, long text, number, single/multiple choice, date, Date (Today), date & time, time, yes/no, email, Phone Number, URL, Fixed Value, Group, Distributor, End User, Brand, Client Email, Row Creator, Recent Row Modifier, and Intercolumn Value Controller.</div>
            <div><button className="button">+ Add Column</button></div>
          </form>
        </div>
      </aside>
    </div>
  </div>;
}
