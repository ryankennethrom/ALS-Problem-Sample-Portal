export type QueueSearchItem = {
  problem_number: number;
  table_name?: string;
  container_id?: string;
  workflow_status?: string;
  distributor?: string;
  end_user?: string;
  brand?: string;
  als_tracking_number?: string;
  courier?: string;
  courier_tracking_number?: string;
  created_at?: string;
  modified_at?: string;
  custom_values?: Record<string, unknown>;
};

export type QueueAdvancedFilter = {
  field_key: string;
  operator: string;
  value?: string;
  value2?: string;
};

export type QueueMatchMode = 'all' | 'any';

export type QueueFilterField = {
  key: string;
  label: string;
  type: 'text' | 'number' | 'datetime' | 'choice';
  choices?: string[];
};

export const WORKFLOW_QUEUE_FIELDS: QueueFilterField[] = [
  { key: 'problem_number', label: 'Problem ID', type: 'number' },
  { key: 'table_name', label: 'Problem Sample Table', type: 'text' },
  { key: 'workflow_status', label: 'Status', type: 'choice', choices: [
    'Automatically Disposed',
    'Halted Automatic Disposal',
    'To be Disposed',
    'To be shipped back to client',
    'Shipped back to client',
    'To be back to testing',
    'Back to testing',
    'Disposed',
  ] },
  { key: 'container_id', label: 'Container ID', type: 'text' },
  { key: 'distributor', label: 'Distributor', type: 'text' },
  { key: 'end_user', label: 'End User', type: 'text' },
  { key: 'brand', label: 'Brand', type: 'text' },
  { key: 'als_tracking_number', label: 'ALS Tracking Number', type: 'text' },
  { key: 'courier', label: 'Courier', type: 'text' },
  { key: 'courier_tracking_number', label: 'Courier Tracking Number', type: 'text' },
  { key: 'created_at', label: 'Created At', type: 'datetime' },
  { key: 'modified_at', label: 'Modified At', type: 'datetime' },
  { key: 'any_custom', label: 'Any Custom Field', type: 'text' },
];

function textValue(value: unknown) {
  if (value == null) return '';
  if (Array.isArray(value)) return value.join(' ');
  if (typeof value === 'object') return Object.values(value as Record<string, unknown>).map(textValue).join(' ');
  return String(value);
}

function normalizeText(value: unknown) {
  return textValue(value)
    .normalize('NFKC')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}@.]+/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function normalizeIdentifier(value: unknown) {
  return textValue(value).normalize('NFKC').toUpperCase().replace(/[^A-Z0-9]/g, '');
}

function problemNumberFromQuery(query: string) {
  const match = query.normalize('NFKC').match(/^\s*(?:problem\s*(?:id)?\s*)?#?\s*(\d+)\s*$/i);
  return match ? Number(match[1]) : null;
}

export function matchesWorkflowQueueSearch(item: QueueSearchItem, query: string) {
  const raw = query.trim();
  if (!raw) return true;

  const requestedProblemNumber = problemNumberFromQuery(raw);
  if (requestedProblemNumber !== null && item.problem_number === requestedProblemNumber) return true;

  const needle = normalizeText(raw);
  const identifierNeedle = normalizeIdentifier(raw);
  const dynamicValues = Object.values(item.custom_values || {});
  const values: unknown[] = [
    `Problem #${item.problem_number}`,
    `Problem ${item.problem_number}`,
    item.problem_number,
    item.table_name,
    item.container_id,
    item.workflow_status,
    item.distributor,
    item.end_user,
    item.brand,
    item.als_tracking_number,
    item.courier,
    item.courier_tracking_number,
    ...dynamicValues,
  ];

  return values.some(value => {
    const haystack = normalizeText(value);
    if (needle && haystack.includes(needle)) return true;
    const identifier = normalizeIdentifier(value);
    return Boolean(identifierNeedle && identifier && identifier.includes(identifierNeedle));
  });
}

function valueFor(item: QueueSearchItem, fieldKey: string): unknown {
  if (fieldKey === 'any_custom') return Object.values(item.custom_values || {}).map(textValue).join(' ');
  return (item as unknown as Record<string, unknown>)[fieldKey];
}

function empty(value: unknown) {
  return value == null || value === '' || (Array.isArray(value) && value.length === 0);
}

function compare(item: QueueSearchItem, filter: QueueAdvancedFilter, field: QueueFilterField) {
  const actual = valueFor(item, field.key);
  const operator = filter.operator;
  if (operator === 'is_empty') return empty(actual);
  if (operator === 'is_not_empty') return !empty(actual);
  if (empty(actual)) return false;

  if (field.type === 'number') {
    const left = Number(actual);
    const right = Number(filter.value);
    if (!Number.isFinite(left) || !Number.isFinite(right)) return false;
    if (operator === 'equals') return left === right;
    if (operator === 'not_equals') return left !== right;
    if (operator === 'gt') return left > right;
    if (operator === 'gte') return left >= right;
    if (operator === 'lt') return left < right;
    if (operator === 'lte') return left <= right;
    if (operator === 'between') {
      const upper = Number(filter.value2);
      if (!Number.isFinite(upper)) return false;
      const low = Math.min(right, upper);
      const high = Math.max(right, upper);
      return left >= low && left <= high;
    }
    return false;
  }

  if (field.type === 'datetime') {
    const left = new Date(String(actual)).getTime();
    const right = new Date(String(filter.value || '')).getTime();
    if (!Number.isFinite(left) || !Number.isFinite(right)) return false;
    if (operator === 'equals') return left === right;
    if (operator === 'not_equals') return left !== right;
    if (operator === 'before') return left < right;
    if (operator === 'after') return left > right;
    if (operator === 'between') {
      const upper = new Date(String(filter.value2 || '')).getTime();
      if (!Number.isFinite(upper)) return false;
      const low = Math.min(right, upper);
      const high = Math.max(right, upper);
      return left >= low && left <= high;
    }
    return false;
  }

  if (field.type === 'choice') {
    const left = textValue(actual);
    const right = textValue(filter.value);
    if (operator === 'equals') return left === right;
    if (operator === 'not_equals') return left !== right;
    return false;
  }

  const left = normalizeText(actual);
  const right = normalizeText(filter.value || '');
  if (operator === 'contains') return left.includes(right);
  if (operator === 'not_contains') return !left.includes(right);
  if (operator === 'equals') return left === right;
  if (operator === 'not_equals') return left !== right;
  if (operator === 'starts_with') return left.startsWith(right);
  if (operator === 'ends_with') return left.endsWith(right);
  return false;
}

export function matchesWorkflowQueueAdvanced(
  item: QueueSearchItem,
  filters: QueueAdvancedFilter[],
  matchMode: QueueMatchMode,
) {
  if (!filters.length) return true;
  const fieldMap = new Map(WORKFLOW_QUEUE_FIELDS.map(field => [field.key, field]));
  const checks = filters.map(filter => {
    const field = fieldMap.get(filter.field_key);
    return field ? compare(item, filter, field) : false;
  });
  return matchMode === 'any' ? checks.some(Boolean) : checks.every(Boolean);
}
