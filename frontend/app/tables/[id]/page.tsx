'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { queueToastForReload } from '@/lib/toast';
import { COLUMN_TYPES, ColumnType, GroupRole, GroupUser, ProblemColumn, ProblemTable } from '@/lib/problemTables';
import DistributorAutocomplete from '@/components/DistributorAutocomplete';
import EndUserAutocomplete from '@/components/EndUserAutocomplete';
import ClientEmailAutocomplete from '@/components/ClientEmailAutocomplete';
import BrandAutocomplete from '@/components/BrandAutocomplete';

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
  if (type === 'row_creator' || type === 'recent_row_modifier') return null;
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
    : type === 'date' ? 'date'
    : type === 'datetime' ? 'datetime-local'
    : type === 'time' ? 'time'
    : type === 'email' ? 'email'
    : type === 'url' ? 'url'
    : 'text';

  return <div className="field"><label htmlFor={id}>Default value</label><input id={id} className="input" type={inputType} step={type === 'number' ? 'any' : undefined} value={value == null ? '' : String(value)} onChange={e => onChange(e.target.value)} placeholder={['text', 'email', 'url'].includes(type) ? 'Optional' : undefined} /></div>;
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

function ColumnEditor({ column, allColumns, onChanged }: {column: ProblemColumn; allColumns: ProblemColumn[]; onChanged: () => Promise<void>}) {
  const [name, setName] = useState(column.name);
  const [columnDescription, setColumnDescription] = useState(column.description || '');
  const [type, setType] = useState<ColumnType>(column.column_type);
  const [choices, setChoices] = useState(column.choices.join('\n'));
  const [defaultValue, setDefaultValue] = useState<unknown>(column.default_value);
  const [groupRole, setGroupRole] = useState<GroupRole>((column.group_role || 'lab_technician') as GroupRole);
  const [dependencyIds, setDependencyIds] = useState<string[]>(column.client_email_dependencies || (column.depends_on_column ? [column.depends_on_column] : []));
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
        default_value: (type === 'row_creator' || type === 'recent_row_modifier') ? null : (type === 'client_email' && dependencyIds.length ? null : normalizeDefault(type, defaultValue)),
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
  }

  return <div className="column-editor">
    <div className="column-editor-grid">
      <div className="field"><label>Name</label><input className="input" value={name} onChange={e=>setName(e.target.value)}/></div>
      <div className="field"><label>Type</label><select className="select" value={type} onChange={e=>changeType(e.target.value as ColumnType)}>{COLUMN_TYPES.map(t=><option key={t.value} value={t.value}>{t.label}</option>)}</select></div>
      <div className="field column-description-field"><label>Explanation <span className="muted">(optional)</span></label><textarea className="textarea compact-textarea" value={columnDescription} onChange={e=>setColumnDescription(e.target.value)} placeholder="Explain what this column is for or what users should enter. An (i) icon appears anywhere the column is shown." /></div>
      {(type === 'choice' || type === 'multi_choice') && <div className="field column-choice-options"><label>Choices (one per line)</label><textarea className="textarea compact-textarea" value={choices} onChange={e=>setChoices(e.target.value)}/></div>}
      {type === 'group' && <div className="field"><label>Group <span className="required-marker" aria-hidden="true"> *</span></label><select className="select" value={groupRole} onChange={e=>{ setGroupRole(e.target.value as GroupRole); setDefaultValue(''); }}><option value="lab_technician">Lab Technician</option><option value="customer_service">Customer Service</option></select></div>}
      {type === 'client_email' && <ClientEmailDependencyPriority value={dependencyIds} onChange={next => { setDependencyIds(next); setDefaultValue(''); }} columns={allColumns} excludeId={column.id} />}
      <DefaultValueField type={type} choices={choiceList} value={defaultValue} onChange={setDefaultValue} idSuffix={column.id} groupRole={groupRole} dependencyConfigured={type === 'client_email' && dependencyIds.length > 0} />
      <div className="column-flags"><label className="check-label"><input type="checkbox" checked={type === 'fixed' ? true : (type === 'row_creator' || type === 'recent_row_modifier') ? false : required} disabled={type === 'fixed' || type === 'row_creator' || type === 'recent_row_modifier'} onChange={e=>setRequired(e.target.checked)}/> Required</label><label className="check-label"><input type="checkbox" checked={searchable} onChange={e=>setSearchable(e.target.checked)}/> Include in search</label><label className="check-label"><input type="checkbox" checked={includeInCustomerNotification} onChange={e=>setIncludeInCustomerNotification(e.target.checked)}/> Include in customer notification</label></div>
    </div>
    <div className="muted result-meta" style={{marginTop:6}}>{type === 'fixed' ? 'This value is read-only on rows. Changing it here updates every existing row in this table.' : type === 'row_creator' ? 'Read-only on rows. The server stores the email of the user who originally created each row, and that value cannot be changed later.' : type === 'recent_row_modifier' ? 'Read-only on rows. The server updates this value to the email of the user who most recently saves the row.' : type === 'group' ? 'Each row can select one user who currently belongs to the configured group.' : type === 'distributor' ? 'Each row uses fuzzy autocomplete against companies whose CoyType is Distributor.' : type === 'end_user' ? 'Each row uses fuzzy autocomplete against companies whose CoyType is End User.' : type === 'brand' ? 'Each row uses fuzzy autocomplete against distinct Brand values in the current Customer Export.' : type === 'client_email' ? (dependencyIds.length ? 'The row loads the active dependency company’s emails into a selectable list. Users can keep/delete selected addresses, clear all, add an email, and fuzzy-filter the list.' : 'Client Email is a multi-address list. Without dependencies, fuzzy search can discover imported emails and Keep Selected stores the chosen addresses.') : 'The default is used for newly created rows. Changing it here does not overwrite existing row values.'}</div>
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
  const [required, setRequired] = useState(false);
  const [searchable, setSearchable] = useState(true);
  const [includeInCustomerNotification, setIncludeInCustomerNotification] = useState(false);

  async function load() {
    const d: ProblemTable = await api(`/problem-tables/${id}/`);
    setTable(d); setName(d.name); setDescription(d.description || ''); setPtDays(d.pt_days ?? 30);
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
        default_value: (colType === 'row_creator' || colType === 'recent_row_modifier') ? null : (colType === 'client_email' && colDependencyIds.length ? null : normalizeDefault(colType, defaultValue)),
      }), successMessage:'Column added successfully.', errorMessage:'Could not add column'});
      setColName('');
      setColDescription('');
      setColType('text');
      setChoices('');
      setDefaultValue('');
      setColGroupRole('lab_technician');
      setColDependencyIds([]);
      setRequired(false);
      setSearchable(true);
      setIncludeInCustomerNotification(false);
      await load();
    } catch(e) { setError(e instanceof Error ? e.message : 'Failed to add column'); }
  }

  async function deleteTable() {
    if (!table || !confirm(`Delete table "${table.name}"? Only empty non-default tables can be deleted.`)) return;
    try { await api(`/problem-tables/${id}/`, {method:'DELETE', successMessage:'Problem sample table deleted successfully.', errorMessage:'Could not delete problem sample table'}); router.push('/tables'); }
    catch(e) { setError(e instanceof Error ? e.message : 'Could not delete table'); }
  }

  function changeNewColumnType(next: ColumnType) {
    setColType(next);
    setDefaultValue(blankDefault(next));
    setRequired(next === 'fixed');
    if (next === 'group') setColGroupRole('lab_technician');
    setColDependencyIds([]);
  }

  if (!table) return <div>{error || 'Loading…'}</div>;
  const newChoiceList = choices.split('\n').map(x=>x.trim()).filter(Boolean);

  return <div>
    <div className="page-toolbar">
      <div><div className="eyebrow">Table settings</div><h1 className="page-heading" style={{marginBottom:0}}>{table.name}</h1></div>
      <div className="toolbar-actions"><Link className="button secondary" href={`/?table=${table.id}`}>Open Table</Link>{!table.is_default && <button className="button danger" onClick={deleteTable}>Delete Table</button>}</div>
    </div>

    {error && <div className="card error" style={{marginBottom:14}}>{error}</div>}

    <div className="two-col table-settings-layout">
      <div className="stack">
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
            <div className="field"><label>Problem Sample Expiration Period (days)</label><input className="input" type="number" min={0} max={3650} value={ptDays} onChange={e=>{ const value = Number(e.target.value); setPtDays(Number.isFinite(value) ? Math.min(3650, Math.max(0, value)) : 0); }} required/><div className="muted result-meta">Each time a sample changes to Automatically Disposed, a new expiration period of this many days starts. Enter 0 for immediate eligibility.</div></div>
            <div className="muted result-meta">Problem Sample Tracking Links remain available for 30 days after the most recent change to Halted Automatic Disposal, To be Disposed, To be shipped back to client, To be back to testing, Back to testing, Disposed, or Shipped back to client. Returning to Automatically Disposed clears that expiry clock and returns the tracking link to its pre-response state.</div>
            <div><button className="button">Save Table Details</button></div>
          </form>
        </section>
        <section className="panel">
          <div className="panel-header">Statuses</div>
          <div className="panel-body stack">
            <div className="muted result-meta">Status is a fixed system field. These are the only allowed values and they cannot be added to, renamed, or removed.</div>
            <div className="status-settings-list">
              {['Automatically Disposed','Halted Automatic Disposal','To be Disposed','To be shipped back to client','To be back to testing','Back to testing','Disposed','Shipped back to client'].map(label => <div className="status-settings-row" key={label}><input className="input" value={label} disabled readOnly/><span className="badge blue">Fixed</span></div>)}
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
            {colType === 'group' && <div className="field"><label>Group <span className="required-marker" aria-hidden="true"> *</span></label><select className="select" value={colGroupRole} onChange={e=>{ setColGroupRole(e.target.value as GroupRole); setDefaultValue(''); }}><option value="lab_technician">Lab Technician</option><option value="customer_service">Customer Service</option></select></div>}
            {colType === 'client_email' && <ClientEmailDependencyPriority value={colDependencyIds} onChange={next => { setColDependencyIds(next); setDefaultValue(''); }} columns={table.columns} />}
            <DefaultValueField type={colType} choices={newChoiceList} value={defaultValue} onChange={setDefaultValue} groupRole={colGroupRole} dependencyConfigured={colType === 'client_email' && colDependencyIds.length > 0} />
            <div className="muted result-meta">{colType === 'fixed' ? 'The fixed value is applied to every existing row and every future row, and cannot be edited from a problem sample.' : colType === 'row_creator' ? 'The value is filled automatically with the email of the user who created each row. Existing rows are backfilled from their recorded creator, and users cannot edit this field.' : colType === 'recent_row_modifier' ? 'The value is filled automatically with the email of the user who most recently saved the row. Existing rows are backfilled from their recorded modifier, and users cannot edit this field.' : colType === 'group' ? 'Choose which employee group this column draws from. Row values are users registered in that group.' : colType === 'distributor' ? 'Row values use fuzzy company-name suggestions restricted to CoyType = Distributor.' : colType === 'end_user' ? 'Row values use fuzzy company-name suggestions restricted to CoyType = End User.' : colType === 'brand' ? 'Row values use fuzzy suggestions from distinct Brand values in the current Customer Export.' : colType === 'client_email' ? (colDependencyIds.length ? 'Dependencies are checked from highest to lowest priority. The first company with imported emails seeds a multi-email list that users can keep, remove, clear, or extend manually.' : 'Without dependencies, users can fuzzy-search the imported customer directory and keep multiple email addresses.') : 'When the column is added, this value fills the column for existing rows and pre-fills it for future problem samples.'}</div>
            <label className="check-label"><input type="checkbox" checked={colType === 'fixed' ? true : (colType === 'row_creator' || colType === 'recent_row_modifier') ? false : required} disabled={colType === 'fixed' || colType === 'row_creator' || colType === 'recent_row_modifier'} onChange={e=>setRequired(e.target.checked)}/> Required value</label>
            <label className="check-label"><input type="checkbox" checked={searchable} onChange={e=>setSearchable(e.target.checked)}/> Include this column in fuzzy search</label>
            <label className="check-label"><input type="checkbox" checked={includeInCustomerNotification} onChange={e=>setIncludeInCustomerNotification(e.target.checked)}/> Include in customer notification</label>
            <div className="muted result-meta">Supported types: text, long text, number, single/multiple choice, date, date & time, time, yes/no, email, URL, Fixed Value, Group, Distributor, End User, Brand, Client Email, Row Creator, and Recent Row Modifier.</div>
            <div><button className="button">+ Add Column</button></div>
          </form>
        </div>
      </aside>
    </div>
  </div>;
}
