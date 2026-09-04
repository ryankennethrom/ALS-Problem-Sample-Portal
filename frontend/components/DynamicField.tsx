'use client';

import { ProblemColumn } from '@/lib/problemTables';
import DistributorAutocomplete from '@/components/DistributorAutocomplete';
import EndUserAutocomplete from '@/components/EndUserAutocomplete';
import ClientEmailAutocomplete from '@/components/ClientEmailAutocomplete';
import BrandAutocomplete from '@/components/BrandAutocomplete';
import ColumnInfo from '@/components/ColumnInfo';

function ColumnFieldLabel({
  column,
  htmlFor,
  suffix,
}: {
  column: ProblemColumn;
  htmlFor?: string;
  suffix?: string;
}) {
  const content = <>{column.name}{suffix && <span className="muted"> {suffix}</span>}{column.required && <span className="required-marker" aria-hidden="true"> *</span>}</>;
  return <div className="field-label-row">
    {htmlFor ? <label htmlFor={htmlFor}>{content}</label> : <span className="field-label-text">{content}</span>}
    <ColumnInfo text={column.description} label={column.name} />
  </div>;
}

export default function DynamicField({ column, value, allValues = {}, onChange }: { column: ProblemColumn; value: unknown; allValues?: Record<string, unknown>; onChange: (value: unknown) => void }) {
  const id = `custom-${column.id}`;
  const common = { id, required: column.required };

  if (column.column_type === 'fixed') {
    return <div className="field readonly-field"><ColumnFieldLabel column={column} htmlFor={id} suffix="(fixed)"/><input id={id} className="input readonly-input" value={String(column.default_value ?? '')} disabled readOnly aria-disabled="true" /></div>;
  }
  if (column.column_type === 'row_creator') {
    const creator = value == null || value === '' ? 'Assigned to you when saved' : String(value);
    return <div className="field readonly-field"><ColumnFieldLabel column={column} htmlFor={id} suffix="(row creator)"/><input id={id} className="input readonly-input" value={creator} disabled readOnly aria-disabled="true" /></div>;
  }
  if (column.column_type === 'recent_row_modifier') {
    const modifier = value == null || value === '' ? 'Assigned to you when saved' : String(value);
    return <div className="field readonly-field"><ColumnFieldLabel column={column} htmlFor={id} suffix="(recent row modifier)"/><input id={id} className="input readonly-input" value={modifier} disabled readOnly aria-disabled="true" /></div>;
  }
  if (column.column_type === 'group') {
    const users = column.group_users || [];
    const current = value == null ? '' : String(value);
    const currentIsEligible = users.some(user => user.email.toLowerCase() === current.toLowerCase());
    return <div className="field"><ColumnFieldLabel column={column} htmlFor={id}/><select {...common} className="select" value={current} onChange={e => onChange(e.target.value)}><option value="">-- Select user --</option>{current && !currentIsEligible && <option value={current} disabled>{current} (no longer in group)</option>}{users.map(user => <option key={user.id} value={user.email}>{user.name && user.name.toLowerCase() !== user.email.toLowerCase() ? `${user.name} (${user.email})` : user.email}</option>)}</select><div className="muted result-meta">{column.group_role === 'lab_technician' ? 'Lab Technician' : 'Customer Service'} users</div></div>;
  }
  if (column.column_type === 'distributor') {
    return <div className="field"><ColumnFieldLabel column={column} htmlFor={id}/><DistributorAutocomplete id={id} required={column.required} value={value} onChange={next => onChange(next)} /></div>;
  }
  if (column.column_type === 'end_user') {
    return <div className="field"><ColumnFieldLabel column={column} htmlFor={id}/><EndUserAutocomplete id={id} required={column.required} value={value} onChange={next => onChange(next)} /></div>;
  }
  if (column.column_type === 'brand') {
    return <div className="field"><ColumnFieldLabel column={column} htmlFor={id}/><BrandAutocomplete id={id} required={column.required} value={value} onChange={next => onChange(next)} /></div>;
  }
  if (column.column_type === 'client_email') {
    const dependencies = (column.client_email_dependency_details || []).map(dependency => ({
      id: dependency.id,
      label: dependency.name,
      value: allValues[dependency.field_key],
    }));
    return <div className="field"><ColumnFieldLabel column={column} htmlFor={id}/><ClientEmailAutocomplete
      id={id}
      required={column.required}
      value={value}
      onChange={next => onChange(next)}
      dependencies={dependencies}
    /></div>;
  }
  if (column.column_type === 'long_text') {
    return <div className="field"><ColumnFieldLabel column={column} htmlFor={id}/><textarea {...common} className="textarea" value={String(value ?? '')} onChange={e => onChange(e.target.value)}/></div>;
  }
  if (column.column_type === 'choice') {
    const current = String(value ?? '');
    return <div className="field"><ColumnFieldLabel column={column} htmlFor={id}/><select {...common} className="select" value={current} onChange={e => onChange(e.target.value)}><option value="">-- Select --</option>{column.choices.map(c => <option key={c} value={c}>{c}</option>)}</select></div>;
  }
  if (column.column_type === 'multi_choice') {
    const selected = Array.isArray(value) ? value.map(String) : [];
    return <fieldset className="field choice-fieldset"><legend><ColumnFieldLabel column={column}/></legend><div className="choice-list">{column.choices.map(c => <label className="check-label" key={c}><input type="checkbox" checked={selected.includes(c)} onChange={e => onChange(e.target.checked ? [...selected, c] : selected.filter(x => x !== c))}/><span>{c}</span></label>)}</div></fieldset>;
  }
  if (column.column_type === 'boolean') {
    return <div className="field"><ColumnFieldLabel column={column} htmlFor={id}/><label className="toggle-row"><input id={id} type="checkbox" checked={Boolean(value)} onChange={e => onChange(e.target.checked)}/><span>{value ? 'Yes' : 'No'}</span></label></div>;
  }

  const type = column.column_type === 'number' ? 'number'
    : column.column_type === 'date' ? 'date'
    : column.column_type === 'datetime' ? 'datetime-local'
    : column.column_type === 'time' ? 'time'
    : column.column_type === 'email' ? 'email'
    : column.column_type === 'url' ? 'url'
    : 'text';
  const inputValue = value === null || value === undefined ? '' : String(value);
  return <div className="field"><ColumnFieldLabel column={column} htmlFor={id}/><input {...common} className="input" type={type} step={column.column_type === 'number' ? 'any' : undefined} value={inputValue} onChange={e => onChange(e.target.value)}/></div>;
}
