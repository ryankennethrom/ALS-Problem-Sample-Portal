import { CustomValues, displayCustomValue, ProblemTable } from '@/lib/problemTables';

export type CustomerEmailContext = {
  table?: ProblemTable | null;
  values?: CustomValues;
  problemNumber?: number | string | null;
  tableName?: string;
  additionalTo?: string[];
  cc?: string[];
  trackingUrl?: string;
};

type ProblemDetail = { label: string; value: string; position: number; fieldKey: string };

function normalizeEmails(value: unknown): string[] {
  const raw = Array.isArray(value) ? value : (value == null || value === '' ? [] : [value]);
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

function normalizeLabel(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '');
}

function allProblemDetails(context: CustomerEmailContext): ProblemDetail[] {
  const table = context.table;
  const values = context.values || {};
  if (!table) return [];

  return table.columns
    .filter(column => !column.is_system)
    .map(column => {
      const rawValue = column.column_type === 'fixed'
        ? column.default_value
        : values[column.field_key];
      return {
        label: column.name,
        value: displayCustomValue(column, rawValue),
        position: column.position,
        fieldKey: column.field_key,
      };
    })
    .filter(detail => detail.value && detail.value !== '—')
    .sort((a, b) => a.position - b.position);
}

function customerNotificationDetails(context: CustomerEmailContext): ProblemDetail[] {
  const includedKeys = new Set(
    (context.table?.columns || [])
      .filter(column => !column.is_system && column.include_in_customer_notification)
      .map(column => column.field_key),
  );
  return allProblemDetails(context).filter(detail => includedKeys.has(detail.fieldKey));
}

function findDetail(details: ProblemDetail[], aliases: string[]): ProblemDetail | undefined {
  const normalizedAliases = aliases.map(normalizeLabel);
  return details.find(detail => normalizedAliases.includes(normalizeLabel(detail.label)));
}

function findCustomerEmailColumns(table: ProblemTable | null | undefined) {
  if (!table) return [];
  return table.columns.filter(column => column.column_type === 'client_email' || column.column_type === 'email');
}

export function findCustomerEmails(table: ProblemTable | null | undefined, values: CustomValues): string[] {
  const emailColumns = findCustomerEmailColumns(table);
  if (!emailColumns.length) return [];

  // Prefer Client Email, then fields whose labels clearly indicate customer contact.
  const preferred = emailColumns.find(column => column.column_type === 'client_email')
    || emailColumns.find(column => /customer|client|contact/i.test(column.name));
  const column = preferred || emailColumns[0];
  return normalizeEmails(values[column.field_key]);
}

// Kept for existing call sites; a comma-separated recipient list works with
// mailto/Outlook while Client Email itself is stored as a JSON list.
export function findCustomerEmail(table: ProblemTable | null | undefined, values: CustomValues): string {
  return findCustomerEmails(table, values).join(',');
}

export function buildCustomerEmailContent(email: string | string[], context: CustomerEmailContext = {}) {
  const recipientList = normalizeEmails(email);
  const additionalTo = normalizeEmails(context.additionalTo || []);
  const ccRecipients = normalizeEmails(context.cc || []);
  const toRecipients = normalizeEmails([...recipientList, ...additionalTo]);
  const multipleCustomerContacts = recipientList.length > 1;

  const problemNumber = context.problemNumber == null || context.problemNumber === ''
    ? ''
    : String(context.problemNumber);

  const allDetails = allProblemDetails(context);
  const includedDetails = customerNotificationDetails(context);

  const problemType = findDetail(allDetails, ['Problem Type', 'ProblemType']);
  const sampleTracking = findDetail(allDetails, [
    'ALS Sample Tracking Number',
    'ALS Tracking Number',
    'Sample Tracking Number',
  ]);
  const reasonForHold = findDetail(allDetails, [
    'Reason for Hold',
    'Hold Reason',
    'Reason For Sample Processing Hold',
    'Issue Description',
    'Issue',
  ]);
  const dateReceived = findDetail(allDetails, ['Date Received', 'Received Date']);

  const subjectType = problemType?.value || 'Problem Sample';
  const subject = problemNumber
    ? `${subjectType} / Problem ID #${problemNumber}`
    : `${subjectType} / Problem Sample Notification`;

  const lines: string[] = [];
  lines.push('To Whom It May Concern,');
  lines.push('');
  lines.push('Thank you for submitting your samples to ALS for fluid analysis. We are writing to notify you that we have received the affected sample(s) from your organization; however, we are currently unable to proceed with testing.');

  if (multipleCustomerContacts) {
    lines.push('');
    lines.push('This notification is being sent to multiple contacts because a primary contact for the affected sample(s) could not be confirmed from our records. If another person in your organization should handle this matter, please forward this message to them or let ALS Customer Service know.');
  }

  lines.push('');
  lines.push('Please review the following details regarding the affected sample(s) and the reason for the sample processing hold:');
  if (problemNumber) lines.push(`Problem ID: ${problemNumber}`);
  if (problemType?.value) lines.push(`Problem Type: ${problemType.value}`);
  lines.push(`ALS Sample Tracking Number: ${sampleTracking?.value || 'Not provided'}`);
  lines.push(`Reason for Hold: ${reasonForHold?.value || 'Please contact ALS Customer Service for details'}`);
  lines.push(`Date Received: ${dateReceived?.value || 'Not provided'}`);

  // Preserve the table-level "Include in customer notification" setting for
  // any useful fields beyond the core automation template above.
  const coreFieldKeys = new Set(
    [problemType, sampleTracking, reasonForHold, dateReceived]
      .filter((detail): detail is ProblemDetail => Boolean(detail))
      .map(detail => detail.fieldKey),
  );
  const extraDetails = includedDetails.filter(detail => !coreFieldKeys.has(detail.fieldKey));
  if (extraDetails.length) {
    lines.push('');
    lines.push('Additional information:');
    for (const detail of extraDetails) lines.push(`${detail.label}: ${detail.value}`);
  }

  lines.push('');
  if (context.trackingUrl) {
    lines.push('');
    lines.push('Please review and update this problem sample using the secure Problem Sample Tracking Link below, or contact our Customer Service team at naedm.de@alsglobal.com for assistance:');
    lines.push('');
    lines.push('PROBLEM SAMPLE TRACKING LINK');
    lines.push('');
    lines.push(context.trackingUrl);
    lines.push('');
    lines.push('The Problem Sample Tracking page also shows the available problem sample details, images, and files.');
  } else {
    lines.push('Please contact our Customer Service team at naedm.de@alsglobal.com for assistance.');
  }
  lines.push('');
  const expirationDays = context.table?.pt_days ?? 30;
  if (expirationDays === 0) {
    lines.push('Please note: this notification activates automatic disposal. If no customer action is selected, the sample is eligible for disposal immediately.');
  } else {
    lines.push(`Please note: this notification activates automatic disposal and starts a new ${expirationDays}-day expiration period. If no customer action is selected, the sample becomes eligible for disposal when that period ends.`);
  }
  lines.push('');
  lines.push('We value your partnership and remain committed to processing your samples as efficiently as possible once the reason for the hold identified above has been addressed.');
  lines.push('');
  lines.push('Should you have any questions or require further assistance, please do not hesitate to reach out.');
  lines.push('');
  lines.push('Thank you for your prompt attention to this matter.');
  lines.push('');
  lines.push('Regards,');
  lines.push('ALS');

  return { to: toRecipients, cc: ccRecipients, subject, body: lines.join('\n') };
}

export async function buildCustomerMailto(email: string | string[], context: CustomerEmailContext = {}): Promise<string> {
  const content = buildCustomerEmailContent(email, context);
  const query = [`subject=${encodeURIComponent(content.subject)}`, `body=${encodeURIComponent(content.body)}`];
  if (content.cc.length) query.push(`cc=${encodeURIComponent(content.cc.join(','))}`);
  return `mailto:${content.to.join(',')}?${query.join('&')}`;
}

export function invokeCustomerEmail(mailto: string): void {
  const link = document.createElement('a');
  link.href = mailto;
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  link.remove();
}
