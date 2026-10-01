import { CustomValues, displayCustomValue, ProblemTable } from '@/lib/problemTables';
import { api } from '@/lib/api';

export type CustomerEmailContext = {
  table?: ProblemTable | null;
  values?: CustomValues;
  problemNumber?: number | string | null;
  tableName?: string;
  additionalTo?: string[];
  cc?: string[];
  trackingUrl?: string;
  edmontonRecipient?: string;
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

export type CustomerEmailTemplate = {
  subject_template: string;
  body_template: string;
};

export const DEFAULT_CUSTOMER_EMAIL_TEMPLATE: CustomerEmailTemplate = {
  subject_template: '{{problem_type}} / Ticket ID #{{problem_id}}',
  body_template: `To Whom It May Concern,

Thank you for submitting your samples to ALS for fluid analysis. We are writing to notify you that we have received the affected sample(s) from your organization; however, we are currently unable to proceed with testing.

{{multiple_contacts_notice}}

Please review the following details regarding the affected sample(s) and the reason for the sample processing hold:
{{problem_details}}

{{additional_information}}

Please review and update this ticket using the secure Ticket Tracking Link below, or contact our Customer Service team at {{na_edm_email}} for assistance:

TICKET TRACKING LINK

{{tracking_link}}

The Ticket Tracking page also shows the available ticket details, images, and files.

{{automatic_disposal_notice}}

We value your partnership and remain committed to processing your samples as efficiently as possible once the reason for the hold identified above has been addressed.

Should you have any questions or require further assistance, please do not hesitate to reach out.

Thank you for your prompt attention to this matter.

Regards,
ALS`,
};

function renderTemplate(template: string, values: Record<string, string>): string {
  return template.replace(/{{\s*([a-zA-Z0-9_]+)\s*}}/g, (match, key: string) =>
    Object.prototype.hasOwnProperty.call(values, key) ? values[key] : match,
  ).replace(/\n{3,}/g, '\n\n').trim();
}

async function loadCustomerEmailTemplate(): Promise<CustomerEmailTemplate> {
  try {
    const result = await api('/email-templates/customer-notification/');
    if (result?.subject_template && result?.body_template) {
      return { subject_template: result.subject_template, body_template: result.body_template };
    }
  } catch {
    // Keep customer notification available if template retrieval is temporarily
    // unavailable. The built-in copy matches the seeded server template.
  }
  return DEFAULT_CUSTOMER_EMAIL_TEMPLATE;
}

export function buildCustomerEmailContent(
  email: string | string[],
  context: CustomerEmailContext = {},
  template: CustomerEmailTemplate = DEFAULT_CUSTOMER_EMAIL_TEMPLATE,
) {
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

  const subjectType = problemType?.value || 'Ticket';
  const coreFieldKeys = new Set(
    [problemType, sampleTracking, reasonForHold, dateReceived]
      .filter((detail): detail is ProblemDetail => Boolean(detail))
      .map(detail => detail.fieldKey),
  );
  const extraDetails = includedDetails.filter(detail => !coreFieldKeys.has(detail.fieldKey));
  const additionalInformation = extraDetails.length
    ? ['Additional information:', ...extraDetails.map(detail => `${detail.label}: ${detail.value}`)].join('\n')
    : '';

  const problemDetailLines: string[] = [];
  if (problemNumber) problemDetailLines.push(`Ticket ID: ${problemNumber}`);
  if (problemType?.value) problemDetailLines.push(`Problem Type: ${problemType.value}`);
  problemDetailLines.push(`ALS Sample Tracking Number: ${sampleTracking?.value || 'Not provided'}`);
  problemDetailLines.push(`Reason for Hold: ${reasonForHold?.value || 'Please contact ALS Customer Service for details'}`);
  problemDetailLines.push(`Date Received: ${dateReceived?.value || 'Not provided'}`);

  const expirationDays = context.table?.pt_days ?? 30;
  const automaticDisposalNotice = expirationDays === 0
    ? 'Please note: this notification activates automatic disposal. If no customer action is selected, Current Workflow will be changed to To be Disposed immediately.'
    : `Please note: this notification activates automatic disposal and starts a new ${expirationDays}-day expiration period. If no customer action is selected, Current Workflow will be changed to To be Disposed when that period ends.`;

  const multipleContactsNotice = multipleCustomerContacts
    ? 'This notification is being sent to multiple contacts because a primary contact for the affected sample(s) could not be confirmed from our records. If another person in your organization should handle this matter, please forward this message to them or let ALS Customer Service know.'
    : '';

  const values: Record<string, string> = {
    na_edm_email: context.edmontonRecipient || 'NAEDM.DE@ALSGlobal.com',
    problem_id: problemNumber,
    problem_type: subjectType,
    als_sample_tracking_number: sampleTracking?.value || 'Not provided',
    reason_for_hold: reasonForHold?.value || 'Please contact ALS Customer Service for details',
    date_received: dateReceived?.value || 'Not provided',
    problem_details: problemDetailLines.join('\n'),
    additional_information: additionalInformation,
    multiple_contacts_notice: multipleContactsNotice,
    tracking_link: context.trackingUrl || '',
    automatic_disposal_notice: automaticDisposalNotice,
  };

  const subject = renderTemplate(template.subject_template, values);
  const body = renderTemplate(template.body_template, values);
  return { to: toRecipients, cc: ccRecipients, subject, body };
}

export type CustomerEmailContent = ReturnType<typeof buildCustomerEmailContent>;

export function mailtoForCustomerEmail(content: CustomerEmailContent): string {
  const query = [`subject=${encodeURIComponent(content.subject)}`, `body=${encodeURIComponent(content.body)}`];
  if (content.cc.length) query.push(`cc=${encodeURIComponent(content.cc.join(','))}`);
  return `mailto:${content.to.join(',')}?${query.join('&')}`;
}

export async function prepareCustomerEmail(email: string | string[], context: CustomerEmailContext = {}) {
  const [template, edmontonRecipient] = await Promise.all([
    loadCustomerEmailTemplate(),
    context.edmontonRecipient ? Promise.resolve(context.edmontonRecipient) : api('/email-templates/edmonton-recipient/').then((data: { email: string }) => data.email),
  ]);
  const content = buildCustomerEmailContent(email, { ...context, edmontonRecipient }, template);
  return { content, mailto: mailtoForCustomerEmail(content) };
}

export async function buildCustomerMailto(email: string | string[], context: CustomerEmailContext = {}): Promise<string> {
  return (await prepareCustomerEmail(email, context)).mailto;
}

export function invokeCustomerEmail(mailto: string): void {
  const link = document.createElement('a');
  link.href = mailto;
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  link.remove();
}
