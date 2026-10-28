'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { api, activeLabCode } from '@/lib/api';
import { queueToastForReload } from '@/lib/toast';
import { COLUMN_TYPES, ColumnType, GroupRole, GroupUser, IntercolumnRule, IntercolumnRuleDirection, ProblemColumn, ProblemTable, MaskFieldState, ProblemTypeRules, BrandCCRule } from '@/lib/problemTables';
import DistributorAutocomplete from '@/components/DistributorAutocomplete';
import EndUserAutocomplete from '@/components/EndUserAutocomplete';
import ClientEmailAutocomplete from '@/components/ClientEmailAutocomplete';
import BrandAutocomplete from '@/components/BrandAutocomplete';

const CURRENT_WORKFLOWS = [
  'Follow Up Required',
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
  label = 'Default value',
}: {
  type: ColumnType;
  choices: string[];
  value: unknown;
  onChange: (value: unknown) => void;
  idSuffix?: string;
  groupRole?: GroupRole;
  dependencyConfigured?: boolean;
  label?: string;
}) {
  const id = `column-value-${idSuffix}`;
  const [groupUsers, setGroupUsers] = useState<GroupUser[]>([]);

  useEffect(() => {
    if (type !== 'group') { setGroupUsers([]); return; }
    api(`/auth/users/?role=${encodeURIComponent(groupRole)}`)
      .then(data => setGroupUsers(Array.isArray(data) ? data : []))
      .catch(() => setGroupUsers([]));
  }, [type, groupRole]);

  if (type === 'row_creator' || type === 'recent_row_modifier' || type === 'date_today') return null;
  if (type === 'distributor') {
    return <DistributorAutocomplete id={id} label={label} value={value} onChange={onChange as (value: string) => void} placeholder="Optional distributor…" />;
  }
  if (type === 'brand') {
    return <BrandAutocomplete id={id} label={label} value={value} onChange={onChange as (value: string) => void} placeholder="Optional brand…" />;
  }
  if (type === 'end_user') {
    return <EndUserAutocomplete id={id} label={label} value={value} onChange={onChange as (value: string) => void} placeholder="Optional end user…" />;
  }

  if (type === 'client_email') {
    if (dependencyConfigured) return null;
    return <ClientEmailAutocomplete id={id} label={label} value={value} onChange={onChange as (value: string[]) => void} placeholder="Fuzzy-search client emails…" />;
  }

  if (type === 'fixed') {
    return <div className="field"><label htmlFor={id}>Fixed value <span className="required-marker" aria-hidden="true">*</span></label><input id={id} className="input" value={String(value ?? '')} onChange={e => onChange(e.target.value)} required placeholder="Value shown in every row" /></div>;
  }

  if (type === 'long_text') {
    return <div className="field"><label htmlFor={id}>{label}</label><textarea id={id} className="textarea" value={String(value ?? '')} onChange={e => onChange(e.target.value)} placeholder="Optional" /></div>;
  }

  if (type === 'choice' || type === 'problem_type') {
    return <div className="field"><label htmlFor={id}>{label}</label><select id={id} className="select" value={String(value ?? '')} onChange={e => onChange(e.target.value)}><option value="">-- None --</option>{choices.map(choice => <option key={choice} value={choice}>{choice}</option>)}</select></div>;
  }

  if (type === 'multi_choice') {
    const selected = Array.isArray(value) ? value.map(String) : [];
    return <fieldset className="field choice-fieldset"><legend>{label}</legend><div className="choice-list">{choices.length === 0 && <span className="muted">Add choices above first.</span>}{choices.map(choice => <label className="check-label" key={choice}><input type="checkbox" checked={selected.includes(choice)} onChange={e => onChange(e.target.checked ? [...selected, choice] : selected.filter(item => item !== choice))} /><span>{choice}</span></label>)}</div></fieldset>;
  }

  if (type === 'group') {
    const current = value == null ? '' : String(value);
    return <div className="field"><label htmlFor={id}>{label}</label><select id={id} className="select" value={current} onChange={e => onChange(e.target.value)}><option value="">-- None --</option>{groupUsers.map(user => <option key={user.id} value={user.email}>{user.name && user.name.toLowerCase() !== user.email.toLowerCase() ? `${user.name} (${user.email})` : user.email}</option>)}</select></div>;
  }

  if (type === 'boolean') {
    const current = value === true ? 'true' : value === false ? 'false' : '';
    return <div className="field"><label htmlFor={id}>{label}</label><select id={id} className="select" value={current} onChange={e => onChange(e.target.value === '' ? null : e.target.value === 'true')}><option value="">-- None --</option><option value="true">Yes</option><option value="false">No</option></select></div>;
  }

  const inputType = type === 'number' ? 'number'
    : type === 'date' ? 'date'
    : type === 'datetime' ? 'datetime-local'
    : type === 'time' ? 'time'
    : type === 'email' ? 'email'
    : type === 'phone' ? 'tel'
    : type === 'url' ? 'url'
    : 'text';

  return <div className="field"><label htmlFor={id}>{label}</label><input id={id} className="input" type={inputType} step={type === 'number' ? 'any' : undefined} value={value == null ? '' : String(value)} onChange={e => onChange(e.target.value)} placeholder={['text', 'email', 'phone', 'url'].includes(type) ? 'Optional' : undefined} /></div>;
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

function MaskRulesEditor({
  choices, rules, onChange, columns, excludeId,
}: {
  choices: string[];
  rules: ProblemTypeRules;
  onChange: (next: ProblemTypeRules) => void;
  columns: ProblemColumn[];
  excludeId?: string;
}) {
  const [selectedChoice, setSelectedChoice] = useState('');
  const active = choices.includes(selectedChoice) ? selectedChoice : choices[0];
  const config: {columns: Record<string, MaskFieldState>; images?: MaskFieldState; attachments?: MaskFieldState; customer_details?: string} = (active ? rules[active] : undefined) || {columns: {}};
  const candidates = columns.filter(column =>
    column.id !== excludeId && column.column_type !== 'problem_type' &&
    (!column.is_system || ['current-workflow', 'dispose-automatically'].includes(column.field_key))
  );

  function change(target: string, nextState: string) {
    if (!active) return;
    const next = {...rules};
    const definition: {columns: Record<string, MaskFieldState>; images?: MaskFieldState; attachments?: MaskFieldState; customer_details?: string} = {...config, columns: {...(config.columns || {})}};
    if (target === 'images' || target === 'attachments') {
      if (nextState) definition[target] = nextState as MaskFieldState;
      else delete definition[target];
    } else {
      if (nextState) definition.columns[target] = nextState as MaskFieldState;
      else delete definition.columns[target];
    }
    next[active] = definition;
    onChange(next);
  }

  function changeCustomerDetails(value: string) {
    if (!active) return;
    onChange({...rules, [active]: {...config, customer_details: value}});
  }

  return <div className="field" style={{gridColumn:'1 / -1'}}>
    <label>Problem Type rules</label>
    <div className="muted result-meta" style={{marginBottom:10}}>
      Each choice configures the Create Ticket form and may ask the customer for additional details. Required overrides Shown, which overrides Hidden when multiple masks disagree. "Use normal behavior" does not override another mask. Mask columns always stay visible. A database-required column needs a default value if any choice makes it hidden or optional.
    </div>
    {!choices.length ? <div className="muted">Add at least one choice above to configure its form.</div> : <div className="stack">
      <div className="field"><label>Configure form for choice</label><select className="select" value={active} onChange={event => setSelectedChoice(event.target.value)}>{choices.map(choice => <option value={choice} key={choice}>{choice}</option>)}</select></div>
      <div className="field">
        <label>Questions or instructions for the customer <span className="muted">(optional)</span></label>
        <textarea className="textarea" rows={5} maxLength={8000} value={config.customer_details || ''}
          onChange={event => changeCustomerDetails(event.target.value)}
          placeholder="E.g., Please tell us whether the sample container was damaged, and attach a photo if possible." />
        <div className="muted result-meta">Sent in the ticket tracking email and shown as ALS Edmonton's first chat message for this problem type. Leave blank if no details are needed.</div>
      </div>
      <div className="stack">
        {candidates.map(column => <div className="field" key={column.id}>
          <label>{column.name}{column.required && <span className="muted"> (database-required)</span>}</label>
          <select className="select" value={config.columns?.[column.id] || ''} onChange={event => change(column.id, event.target.value)}>
            <option value="">Use normal behavior</option><option value="hidden">Hidden</option><option value="shown">Shown (optional)</option><option value="required">Shown and required</option>
          </select>
        </div>)}
        {(['images', 'attachments'] as const).map(target => <div className="field" key={target}>
          <label>{target === 'images' ? 'Images' : 'Attachments'}</label>
          <select className="select" value={config[target] || ''} onChange={event => change(target, event.target.value)}>
            <option value="">Use normal behavior</option><option value="hidden">Hidden</option><option value="shown">Shown (optional)</option><option value="required">Shown and required (at least one file)</option>
          </select>
        </div>)}
      </div>
    </div>}
  </div>;
}

function BrandCompanyDependencies({ columns, selected, onChange }: {columns: ProblemColumn[]; selected: string[]; onChange: (ids: string[]) => void}) {
  const available = columns.filter(col => col.column_type === 'distributor' || col.column_type === 'end_user');
  return <div className="field" style={{gridColumn:'1 / -1'}}>
    <label>Other Company fields to check their Brand</label>
    <div className="muted result-meta">Select the ticket's Distributor and/or End User fields. Each company's Brand is looked up by exact company name and type in the current Customer Export. Missing companies do not match.</div>
    {available.length ? available.map(col => <label className="check-label" key={col.id}>
      <input type="checkbox" checked={selected.includes(col.id)} onChange={e => onChange(e.target.checked ? [...selected, col.id] : selected.filter(id => id !== col.id))} />
      {col.name} ({col.column_type === 'distributor' ? 'Distributor' : 'End User'})
    </label>) : <div className="muted result-meta">Add a Distributor or End User column to use company Brand dependencies.</div>}
  </div>;
}

function BrandCCRulesEditor({ rules, onChange, dependencies, columns, columnId, savedRules }: {
  rules: BrandCCRule[];
  onChange: (rules: BrandCCRule[]) => void;
  dependencies: string[];
  columns: ProblemColumn[];
  columnId?: string;
  savedRules?: BrandCCRule[];
}) {
  const router = useRouter();
  const [sendingRule, setSendingRule] = useState<string | null>(null);
  const [reportError, setReportError] = useState('');
  const [labSelectionRule, setLabSelectionRule] = useState<BrandCCRule | null>(null);
  const [labs, setLabs] = useState<{id:number;name:string;code:string}[]>([]);
  const [loadingLabs, setLoadingLabs] = useState(false);
  const [allLabs, setAllLabs] = useState(false);
  const [selectedLabIds, setSelectedLabIds] = useState<number[]>([]);
  const update = (index: number, changes: Partial<BrandCCRule>) =>
    onChange(rules.map((rule, i) => i === index ? { ...rule, ...changes } : rule));

  const isSaved = (rule: BrandCCRule) => {
    if (!columnId || !rule.id) return false;
    const saved = (savedRules || []).find(item => item.id === rule.id);
    return Boolean(saved && saved.send_monthly_reports &&
      saved.match_type === rule.match_type && saved.pattern === rule.pattern &&
      !rule.pending_brand_review && !saved.pending_brand_review &&
      JSON.stringify(saved.sources || ['ticket']) === JSON.stringify(rule.sources || ['ticket']) &&
      JSON.stringify(saved.cc_emails || []) === JSON.stringify((rule.cc_emails || []).filter(Boolean)));
  };

  async function openMonthlyLabPicker(rule: BrandCCRule) {
    if (!isSaved(rule) || sendingRule) return;
    if (activeLabCode() !== 'ALL') {
      await sendNow(rule);
      return;
    }
    setReportError('');
    setSelectedLabIds([]);
    setAllLabs(false);
    setLabSelectionRule(rule);
    setLoadingLabs(true);
    try {
      const available: {id:number;name:string;code:string}[] = await api('/auth/labs/');
      setLabs(Array.isArray(available) ? available : []);
    } catch (error) {
      setReportError(error instanceof Error ? error.message : 'Could not load labs.');
      setLabSelectionRule(null);
    } finally {
      setLoadingLabs(false);
    }
  }

  async function sendNow(rule: BrandCCRule, selection?: {all_labs: boolean; lab_ids?: number[]}) {
    if (!columnId || !rule.id || !isSaved(rule) || sendingRule) return;
    if (activeLabCode() === 'ALL' && (!selection || (!selection.all_labs && !selection.lab_ids?.length))) {
      setReportError('Select at least one lab or All Labs.');
      return;
    }
    setReportError('');
    setSendingRule(rule.id);
    try {
      const result: {email_id: string; email_ids?: string[]} = await api('/system-emails/queue-now/', {
        method: 'POST',
        body: JSON.stringify({column_id: columnId, rule_id: rule.id, request_id: crypto.randomUUID(), ...(selection || {})}),
        errorMessage: 'Could not prepare monthly report',
      });
      setLabSelectionRule(null);
      // Multi-lab selections produce one separate pending draft per lab.
      // Show the entire queue rather than opening just the first draft.
      if ((result.email_ids || []).length > 1) router.push('/send-system-emails');
      else router.push(`/send-system-emails?email=${encodeURIComponent(result.email_id)}`);
    } catch (error) {
      setReportError(error instanceof Error ? error.message : 'Could not prepare monthly report.');
    } finally {
      setSendingRule(null);
    }
  }

  return <div className="field" style={{gridColumn:'1 / -1'}}>
    <label>Brand CC recipients and monthly reports</label>
    <div className="muted result-meta" style={{marginBottom:8}}>
      When any selected Brand source matches, add its recipients in Cc only when sending a tracking link (new tickets or tracking-link resends). Regular customer emails do not automatically CC these recipients.
      Rules are case-insensitive; all matching rules are combined, with duplicates removed.
      Wildcards: * matches any characters; ? matches one character. Enable Send Monthly Reports to queue a monthly summary for these same recipients, filtered to matching Brand tickets. A migrated Distributor rule is inactive until an admin reviews its new Brand filter and saves this column. Reports are reviewed and sent manually under Send System Emails.
    </div>
    <div className="stack">
      {rules.map((rule, i) => <div className="intercolumn-rule-card stack" key={i}>
        {rule.pending_brand_review && <div className="error">Migrated Distributor-name rule: its pattern previously matched the company name, not its Brand. Review the Brand pattern and selected sources, then save this column to activate it. It is temporarily inactive to prevent incorrect CC emails.</div>}
        <div className="intercolumn-rule-header"><strong>CC rule {i + 1}</strong>
          <button className="button danger" type="button" onClick={() => onChange(rules.filter((_, j) => j !== i))}>Remove</button>
        </div>
        <div className="intercolumn-rule-grid">
          <div className="field" style={{gridColumn:'1 / -1'}}>
            <label>Match any of these Brand sources (OR)</label>
            {[{id:'ticket',name:'Ticket Brand'}, ...columns.filter(col => dependencies.includes(col.id)).map(col => ({id:col.id,name:`Brand of ${col.name}`}))].map(source => <label key={source.id} className="check-label">
              <input type="checkbox" checked={(rule.sources || ['ticket']).includes(source.id)} onChange={e => update(i, {sources: e.target.checked ? [...(rule.sources || ['ticket']), source.id] : (rule.sources || ['ticket']).filter(id => id !== source.id)})}/>
              {source.name}
            </label>)}
          </div>
          <div className="field"><label htmlFor={`brand-rule-mode-${i}`}>Match type</label>
            <select id={`brand-rule-mode-${i}`} className="select" value={rule.match_type} onChange={e => update(i, {match_type: e.target.value as BrandCCRule['match_type']})}>
              <option value="exact">Exactly equals</option>
              <option value="contains">Contains</option>
              <option value="starts_with">Starts with</option>
              <option value="ends_with">Ends with</option>
              <option value="wildcard">Wildcard (* and ?)</option>
            </select>
          </div>
          <div className="field"><label htmlFor={`brand-rule-pattern-${i}`}>Brand pattern</label>
            <input id={`brand-rule-pattern-${i}`} className="input" maxLength={160} value={rule.pattern} onChange={e => update(i, {pattern: e.target.value})} placeholder="e.g. Acme*" />
          </div>
        </div>
        <div className="field"><label htmlFor={`brand-rule-cc-${i}`}>CC email addresses (one per line)</label>
          <textarea id={`brand-rule-cc-${i}`} className="textarea compact-textarea" rows={3} value={(rule.cc_emails || []).join('\n')}
            onChange={e => update(i, {cc_emails: e.target.value.split(/[\n;,]+/).map(x => x.trim())})}
            placeholder={'support@example.com\nmanager@example.com'} />
        </div>
        <label className="checkbox-label" style={{display:'flex',alignItems:'center',gap:9}}>
          <input type="checkbox" checked={Boolean(rule.send_monthly_reports)} onChange={e => update(i, {send_monthly_reports: e.target.checked})} />
          <strong>Send Monthly Reports</strong>
        </label>
        {rule.send_monthly_reports && <div className="stack" style={{gap:8}}>
          <div className="muted result-meta">On the 1st of each month, queue one report for the prior calendar month. To send immediately, prepare a month-to-date report (from the 1st through today), then review and send it in Send System Emails.</div>
          <div><button type="button" className="button secondary" disabled={!isSaved(rule) || Boolean(sendingRule)} onClick={() => void openMonthlyLabPicker(rule)}>
            {sendingRule === rule.id ? 'Preparing report…' : 'Send Monthly Email Now'}
          </button></div>
          {!isSaved(rule) && <div className="muted result-meta">Save this Brand column and its CC rules before generating a report.</div>}
        </div>}
      </div>)}
      {labSelectionRule && <div className="change-reason-overlay" role="presentation" onMouseDown={event => {
        if (event.target === event.currentTarget && !sendingRule) setLabSelectionRule(null);
      }}>
        <section className="change-reason-dialog" role="dialog" aria-modal="true" aria-labelledby="monthly-lab-selection-title" style={{maxHeight:'85vh',overflowY:'auto'}}>
          <h2 id="monthly-lab-selection-title">Send Monthly Email Now — Choose Labs</h2>
          <p className="change-reason-copy">Choose the labs to include. The app will prepare a separate month-to-date email for each selected lab. Emails remain pending for staff review and sending.</p>
          {loadingLabs ? <p className="muted">Loading labs…</p> : <fieldset className="field" disabled={Boolean(sendingRule)}>
            <legend>Report labs</legend>
            <label className="check-label" style={{fontWeight:600}}>
              <input type="checkbox" checked={allLabs} onChange={event => {
                setAllLabs(event.target.checked);
                if (event.target.checked) setSelectedLabIds([]);
              }} /> All Labs ({labs.length})
            </label>
            {!labs.length && <p className="muted">No labs available.</p>}
            {labs.map(lab => <label className="check-label" key={lab.id}>
              <input type="checkbox" disabled={allLabs} checked={allLabs || selectedLabIds.includes(lab.id)} onChange={event =>
                setSelectedLabIds(current => event.target.checked ? [...current, lab.id] : current.filter(id => id !== lab.id))
              } /> {lab.name} ({lab.code})
            </label>)}
          </fieldset>}
          {reportError && <p className="error" role="alert">{reportError}</p>}
          <div className="change-reason-actions">
            <button type="button" className="button secondary" disabled={Boolean(sendingRule)} onClick={() => setLabSelectionRule(null)}>Cancel</button>
            <button type="button" className="button" disabled={loadingLabs || Boolean(sendingRule) || !labs.length || (!allLabs && !selectedLabIds.length)}
              onClick={() => void sendNow(labSelectionRule, allLabs ? {all_labs:true} : {all_labs:false, lab_ids:selectedLabIds})}>
              {sendingRule ? 'Preparing reports…' : `Prepare ${allLabs ? labs.length : selectedLabIds.length} report(s)`}
            </button>
          </div>
        </section>
      </div>}
      {reportError && !labSelectionRule && <p className="error" role="alert">{reportError}</p>}
      {rules.length < 30 && <div><button type="button" className="button secondary" onClick={() => onChange([...rules, {sources:['ticket'], match_type:'contains', pattern:'', cc_emails:[], send_monthly_reports:false}])}>+ Add CC rule</button></div>}
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
  const [maskRules, setMaskRules] = useState<ProblemTypeRules>(column.form_mask_rules || {});
  const [brandCCRules, setBrandCCRules] = useState<BrandCCRule[]>(column.brand_cc_rules || []);
  const [companyBrandDependencies, setCompanyBrandDependencies] = useState<string[]>(column.company_brand_dependencies || []);
  useEffect(() => {
    setBrandCCRules(column.brand_cc_rules || []);
    setCompanyBrandDependencies(column.company_brand_dependencies || []);
  }, [column.brand_cc_rules, column.company_brand_dependencies]);
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
        form_mask_rules: type === 'problem_type' ? Object.fromEntries(Object.entries(maskRules).filter(([choice]) => choiceList.includes(choice))) : {},
        company_brand_dependencies: type === 'brand' ? companyBrandDependencies : [],
        brand_cc_rules: type === 'brand' ? brandCCRules.map(rule => ({...rule, cc_emails: rule.cc_emails.filter(Boolean)})) : [],
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
    if (next !== 'problem_type') setMaskRules({});
    if (next !== 'brand') { setBrandCCRules([]); setCompanyBrandDependencies([]); }
  }

  return <div className="column-editor">
    <div className="column-editor-grid">
      <div className="field"><label>Name</label><input className="input" value={name} onChange={e=>setName(e.target.value)}/></div>
      <div className="field"><label>Type</label><select className="select" value={type} onChange={e=>changeType(e.target.value as ColumnType)}>{COLUMN_TYPES.map(t=><option key={t.value} value={t.value}>{t.label}</option>)}</select></div>
      <div className="field column-description-field"><label>Explanation <span className="muted">(optional)</span></label><textarea className="textarea compact-textarea" value={columnDescription} onChange={e=>setColumnDescription(e.target.value)} placeholder="Explain what this column is for or what users should enter. An (i) icon appears anywhere the column is shown." /></div>
      {(type === 'choice' || type === 'multi_choice' || type === 'problem_type') && <div className="field column-choice-options"><label>Choices (one per line)</label><textarea className="textarea compact-textarea" value={choices} onChange={e=>setChoices(e.target.value)}/></div>}
      {type === 'group' && <div className="field"><label>Group <span className="required-marker" aria-hidden="true"> *</span></label><select className="select" value={groupRole} onChange={e=>{ setGroupRole(e.target.value as GroupRole); setDefaultValue(''); }}><option value="lab_technician">Lab</option><option value="customer_service">Customer Service</option></select></div>}
      {type === 'client_email' && <ClientEmailDependencyPriority value={dependencyIds} onChange={next => { setDependencyIds(next); setDefaultValue(''); }} columns={allColumns} excludeId={column.id} />}
      {type === 'intercolumn_controller' && <IntercolumnRulesEditor rules={intercolumnRules} onChange={setIntercolumnRules} columns={allColumns} controllerName={name} excludeId={column.id} idPrefix={`controller-${column.id}`} />}
      {type === 'problem_type' && <MaskRulesEditor choices={choiceList} rules={maskRules} onChange={setMaskRules} columns={allColumns} excludeId={column.id} />}
      {type === 'brand' && <>
        <BrandCompanyDependencies columns={allColumns} selected={companyBrandDependencies} onChange={next => {setCompanyBrandDependencies(next); setBrandCCRules(rules => rules.map(rule => ({...rule, sources: (rule.sources || ['ticket']).filter(source => source === 'ticket' || next.includes(source))})));}} />
        <BrandCCRulesEditor rules={brandCCRules} onChange={setBrandCCRules} dependencies={companyBrandDependencies} columns={allColumns} columnId={column.id} savedRules={column.brand_cc_rules || []} />
      </>}
      <DefaultValueField type={type} choices={choiceList} value={defaultValue} onChange={setDefaultValue} idSuffix={column.id} groupRole={groupRole} dependencyConfigured={type === 'client_email' && dependencyIds.length > 0} />
      <div className="column-flags"><label className="check-label"><input type="checkbox" checked={type === 'fixed' ? true : (type === 'row_creator' || type === 'recent_row_modifier') ? false : required} disabled={type === 'fixed' || type === 'row_creator' || type === 'recent_row_modifier'} onChange={e=>setRequired(e.target.checked)}/> Required</label><label className="check-label"><input type="checkbox" checked={searchable} onChange={e=>setSearchable(e.target.checked)}/> Include in search</label><label className="check-label"><input type="checkbox" checked={includeInCustomerNotification} onChange={e=>setIncludeInCustomerNotification(e.target.checked)}/> Include in customer email</label></div>
    </div>
    <div className="muted result-meta" style={{marginTop:6}}>{type === 'fixed' ? 'This value is read-only on rows. Changing it here updates every existing row in this table.' : type === 'row_creator' ? 'Read-only on rows. The server stores the email of the user who originally created each row, and that value cannot be changed later.' : type === 'recent_row_modifier' ? 'Read-only on rows. The server shows the staff email/username that most recently saved the row, or Customer when the latest change came from the public tracking link.' : type === 'date_today' ? 'Editable like a normal Date field. New tickets start with the current date automatically; changing this column setting does not overwrite existing valid dates.' : type === 'intercolumn_controller' ? 'This field stores a normal text value and can automatically set or be set by another supported field according to the rules above.' : type === 'group' ? 'Each row can select one user who currently belongs to the configured group.' : type === 'distributor' ? 'Free-text field with fuzzy suggestions from companies whose CoyType is Distributor. Suggestions do not restrict what can be saved.' : type === 'end_user' ? 'Free-text field with fuzzy suggestions from companies whose CoyType is End User. Suggestions do not restrict what can be saved.' : type === 'brand' ? 'Match this ticket Brand and optionally the imported Brand of a Distributor or End User for CC and monthly reports.' : type === 'client_email' ? (dependencyIds.length ? 'The row loads the active dependency company’s emails into a selectable list. Users can keep/delete selected addresses, clear all, add an email, and fuzzy-filter the list.' : 'Client Email is a multi-address list. Without dependencies, fuzzy search can discover imported emails and Keep Selected stores the chosen addresses.') : 'The default is used for newly created rows. Changing it here does not overwrite existing row values.'}</div>
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
  const [fillExistingWith, setFillExistingWith] = useState<unknown>('');
  const [colGroupRole, setColGroupRole] = useState<GroupRole>('lab_technician');
  const [colDependencyIds, setColDependencyIds] = useState<string[]>([]);
  const [colIntercolumnRules, setColIntercolumnRules] = useState<IntercolumnRule[]>([]);
  const [colMaskRules, setColMaskRules] = useState<ProblemTypeRules>({});
  const [colBrandCCRules, setColBrandCCRules] = useState<BrandCCRule[]>([]);
  const [colCompanyBrandDependencies, setColCompanyBrandDependencies] = useState<string[]>([]);
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
        form_mask_rules: colType === 'problem_type' ? Object.fromEntries(Object.entries(colMaskRules).filter(([choice]) => choiceList.includes(choice))) : {},
        company_brand_dependencies: colType === 'brand' ? colCompanyBrandDependencies : [],
        brand_cc_rules: colType === 'brand' ? colBrandCCRules.map(rule => ({...rule, cc_emails: rule.cc_emails.filter(Boolean)})) : [],
        default_value: (colType === 'row_creator' || colType === 'recent_row_modifier' || colType === 'date_today') ? null : (colType === 'client_email' && colDependencyIds.length ? null : normalizeDefault(colType, defaultValue)),
        fill_existing_with: ['fixed', 'row_creator', 'recent_row_modifier', 'date_today'].includes(colType) ? null : normalizeDefault(colType, fillExistingWith),
      }), successMessage:'Column added successfully.', errorMessage:'Could not add column'});
      setColName('');
      setColDescription('');
      setColType('text');
      setChoices('');
      setDefaultValue('');
      setFillExistingWith('');
      setColGroupRole('lab_technician');
      setColDependencyIds([]);
      setColIntercolumnRules([]);
      setColMaskRules({});
      setColBrandCCRules([]);
      setColCompanyBrandDependencies([]);
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
    setFillExistingWith(blankDefault(next));
    setRequired(next === 'fixed');
    if (next === 'group') setColGroupRole('lab_technician');
    setColDependencyIds([]);
    if (next !== 'intercolumn_controller') setColIntercolumnRules([]);
    if (next !== 'problem_type') setColMaskRules({});
    if (next !== 'brand') { setColBrandCCRules([]); setColCompanyBrandDependencies([]); }
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
            <div className="muted result-meta">Ticket Tracking Links remain available for 30 days after the most recent change to a routed disposal, shipping, or back-to-testing Current Workflow. Returning Current Workflow to Follow Up Required clears that expiry clock and makes the tracking link accessible again.</div>
            <div><button className="button">Save Table Details</button></div>
          </form>
        </section>
        <section className="panel">
          <div className="panel-header">Current Workflow</div>
          <div className="panel-body stack">
            <div className="muted result-meta">Current Workflow is the required built-in routing field. These values are fixed because the system uses them for Follow Up Required, disposal, shipping, back-to-testing, and customer tracking:</div>
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
            {(colType === 'choice' || colType === 'multi_choice' || colType === 'problem_type') && <div className="field"><label>Choices (one per line)</label><textarea className="textarea" value={choices} onChange={e=>setChoices(e.target.value)} placeholder={'New\nIn progress\nResolved'}/></div>}
            {colType === 'group' && <div className="field"><label>Group <span className="required-marker" aria-hidden="true"> *</span></label><select className="select" value={colGroupRole} onChange={e=>{ setColGroupRole(e.target.value as GroupRole); setDefaultValue(''); setFillExistingWith(''); }}><option value="lab_technician">Lab</option><option value="customer_service">Customer Service</option></select></div>}
            {colType === 'client_email' && <ClientEmailDependencyPriority value={colDependencyIds} onChange={next => { setColDependencyIds(next); setDefaultValue(''); setFillExistingWith(''); }} columns={table.columns} />}
            {colType === 'intercolumn_controller' && <IntercolumnRulesEditor rules={colIntercolumnRules} onChange={setColIntercolumnRules} columns={table.columns} controllerName={colName} idPrefix="controller-new" />}
            {colType === 'problem_type' && <MaskRulesEditor choices={newChoiceList} rules={colMaskRules} onChange={setColMaskRules} columns={table.columns} />}
            {colType === 'brand' && <>
              <BrandCompanyDependencies columns={table.columns} selected={colCompanyBrandDependencies} onChange={next => {setColCompanyBrandDependencies(next); setColBrandCCRules(rules => rules.map(rule => ({...rule, sources: (rule.sources || ['ticket']).filter(source => source === 'ticket' || next.includes(source))})));}} />
              <BrandCCRulesEditor rules={colBrandCCRules} onChange={setColBrandCCRules} dependencies={colCompanyBrandDependencies} columns={table.columns} />
            </>}
            <DefaultValueField type={colType} choices={newChoiceList} value={defaultValue} onChange={setDefaultValue} groupRole={colGroupRole} dependencyConfigured={colType === 'client_email' && colDependencyIds.length > 0} />
            {!['fixed', 'row_creator', 'recent_row_modifier', 'date_today'].includes(colType) && <>
              <DefaultValueField type={colType} choices={newChoiceList} value={fillExistingWith} onChange={setFillExistingWith} label="Fill existing with" idSuffix="fill-existing-new" groupRole={colGroupRole} dependencyConfigured={false} />
              <div className="muted result-meta">Optional: fill this column on tickets already in this table, once when the column is added. This does not prefill future tickets. For required columns with existing tickets, a value is required here.</div>
            </>}
            <div className="muted result-meta">{colType === 'fixed' ? 'The fixed value is applied to every existing row and every future row, and cannot be edited from a ticket.' : colType === 'row_creator' ? 'The value is filled automatically with the email of the user who created each row. Existing rows are backfilled from their recorded creator, and users cannot edit this field.' : colType === 'recent_row_modifier' ? 'The value is filled automatically with the staff email/username that most recently saved the row, or Customer when the latest change came from the public tracking link. Existing rows are backfilled from their recorded modifier, and users cannot edit this field.' : colType === 'date_today' ? 'Existing rows are filled with today when the column is added. Every new ticket starts with that day’s current date, and staff can edit the date afterward.' : colType === 'intercolumn_controller' ? 'This field stores a normal text value. Add one or more rules to synchronize it with another supported field in either direction or both.' : colType === 'group' ? 'Choose which employee group this column draws from. Row values are users registered in that group.' : colType === 'distributor' ? 'Row values use fuzzy company-name suggestions restricted to CoyType = Distributor.' : colType === 'end_user' ? 'Row values use fuzzy company-name suggestions restricted to CoyType = End User.' : colType === 'brand' ? 'Row values use fuzzy suggestions from Customer Export Brands. Configure CC/monthly rules here and select Company fields whose imported Brands should also match.' : colType === 'client_email' ? (colDependencyIds.length ? 'Dependencies are checked from highest to lowest priority. The first company with imported emails seeds a multi-email list that users can keep, remove, clear, or extend manually.' : 'Without dependencies, users can fuzzy-search the imported customer directory and keep multiple email addresses.') : 'Default value prefills future tickets only. Fill existing with populates existing tickets once when this column is added.'}</div>
            <label className="check-label"><input type="checkbox" checked={colType === 'fixed' ? true : (colType === 'row_creator' || colType === 'recent_row_modifier') ? false : required} disabled={colType === 'fixed' || colType === 'row_creator' || colType === 'recent_row_modifier'} onChange={e=>setRequired(e.target.checked)}/> Required value</label>
            <label className="check-label"><input type="checkbox" checked={searchable} onChange={e=>setSearchable(e.target.checked)}/> Include this column in fuzzy search</label>
            <label className="check-label"><input type="checkbox" checked={includeInCustomerNotification} onChange={e=>setIncludeInCustomerNotification(e.target.checked)}/> Include in customer email</label>
            <div className="muted result-meta">Supported types: text, long text, number, single/multiple choice, date, Date (Today), date & time, time, yes/no, email, Phone Number, URL, Fixed Value, Group, Distributor, End User, Brand, Client Email, Row Creator, Recent Row Modifier, Intercolumn Value Controller, and Problem Type.</div>
            <div><button className="button">+ Add Column</button></div>
          </form>
        </div>
      </aside>
    </div>
  </div>;
}
