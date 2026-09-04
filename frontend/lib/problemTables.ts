export type ColumnType =
  | 'text'
  | 'long_text'
  | 'number'
  | 'choice'
  | 'multi_choice'
  | 'date'
  | 'datetime'
  | 'time'
  | 'boolean'
  | 'email'
  | 'url'
  | 'fixed'
  | 'group'
  | 'distributor'
  | 'end_user'
  | 'client_email'
  | 'row_creator'
  | 'recent_row_modifier'
  | 'brand';

export type GroupRole = 'lab_technician' | 'customer_service';

export type GroupUser = {
  id: number;
  email: string;
  name: string;
  role: GroupRole;
  role_label: string;
};

export type ClientEmailDependency = {
  id: string;
  name: string;
  field_key: string;
  column_type: ColumnType;
  column_type_label: string;
};

export type ProblemColumn = {
  id: string;
  table: string;
  name: string;
  description: string;
  field_key: string;
  column_type: ColumnType;
  column_type_label: string;
  required: boolean;
  searchable: boolean;
  include_in_customer_notification: boolean;
  choices: string[];
  default_value: unknown;
  group_role: GroupRole | '';
  group_users: GroupUser[];
  depends_on_column: string | null;
  depends_on_column_name: string;
  depends_on_field_key: string;
  client_email_dependencies: string[];
  client_email_dependency_details: ClientEmailDependency[];
  position: number;
  is_system: boolean;
};

export type ProblemTable = {
  id: string;
  name: string;
  description: string;
  pt_days: number;
  acknowledgement_link_days: number;
  is_default: boolean;
  columns: ProblemColumn[];
  row_count: number;
};

export type CustomValues = Record<string, unknown>;

export const COLUMN_TYPES: { value: ColumnType; label: string }[] = [
  { value: 'text', label: 'Single line of text' },
  { value: 'long_text', label: 'Multiple lines of text' },
  { value: 'number', label: 'Number' },
  { value: 'choice', label: 'Choice' },
  { value: 'multi_choice', label: 'Multiple choice' },
  { value: 'date', label: 'Date' },
  { value: 'datetime', label: 'Date and time' },
  { value: 'time', label: 'Time' },
  { value: 'boolean', label: 'Yes / No' },
  { value: 'email', label: 'Email' },
  { value: 'url', label: 'URL' },
  { value: 'fixed', label: 'Fixed Value' },
  { value: 'group', label: 'Group' },
  { value: 'distributor', label: 'Distributor' },
  { value: 'end_user', label: 'End User' },
  { value: 'brand', label: 'Brand' },
  { value: 'client_email', label: 'Client Email' },
  { value: 'row_creator', label: 'Row Creator' },
  { value: 'recent_row_modifier', label: 'Recent Row Modifier' },
];

export function initialValue(column: ProblemColumn): unknown {
  if (column.default_value !== null && column.default_value !== undefined) return column.default_value;
  if (column.column_type === 'boolean') return false;
  if (column.column_type === 'multi_choice') return [];
  return '';
}

export function displayCustomValue(column: ProblemColumn, value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (column.column_type === 'group') {
    const email = String(value);
    const user = (column.group_users || []).find(candidate => candidate.email.toLowerCase() === email.toLowerCase());
    if (user && user.name && user.name.toLowerCase() !== user.email.toLowerCase()) return `${user.name} (${user.email})`;
    return user?.email || email;
  }
  if (Array.isArray(value)) return value.join(', ') || '—';
  if (column.column_type === 'boolean') return value ? 'Yes' : 'No';
  if (column.column_type === 'datetime' && typeof value === 'string') {
    const d = new Date(value);
    if (!Number.isNaN(d.valueOf())) return d.toLocaleString();
  }
  return String(value);
}

export function systemColumnHint(column: ProblemColumn): string {
  if (column.field_key === 'problem-id') return 'Auto-incrementing';
  return 'Built-in';
}

export function automaticDisposalDisplay(problem: {
  custom_values?: CustomValues;
  workflow_status?: string;
  status?: string;
  customer_notified_at?: string | null;
  days_until_automatic_disposal?: number | null;
}): string {
  const workflowStatus = String(problem.workflow_status || problem.custom_values?.status || problem.status || '');
  if (workflowStatus !== 'Automatically Disposed') return 'Not automatic';
  const days = problem.days_until_automatic_disposal;
  if (days === null || days === undefined) return '—';
  if (days <= 0) return 'Eligible now';
  return `${days} day${days === 1 ? '' : 's'}`;
}

export function displayProblemValue(
  column: ProblemColumn,
  problem: {
    problem_number: number;
    custom_values?: CustomValues;
    workflow_status?: string;
    status?: string;
    customer_notified_at?: string | null;
    days_until_automatic_disposal?: number | null;
    tracking_url?: string;
    tracking_link_expiry?: string | null;
  },
): string {
  if (column.field_key === 'problem-id') return String(problem.problem_number);
  if (column.field_key === 'system-days-until-automatic-disposal') return automaticDisposalDisplay(problem);
  if (column.field_key === 'system-tracking-link') return problem.tracking_url || '—';
  if (column.field_key === 'system-tracking-link-expiry') {
    if (!problem.tracking_url && !problem.tracking_link_expiry) return '—';
    if (!problem.tracking_link_expiry) return 'Does not expire';
    const d = new Date(problem.tracking_link_expiry);
    return Number.isNaN(d.valueOf()) ? String(problem.tracking_link_expiry) : d.toLocaleString();
  }
  if (column.column_type === 'fixed') return displayCustomValue(column, column.default_value);
  return displayCustomValue(column, problem.custom_values?.[column.field_key]);
}

