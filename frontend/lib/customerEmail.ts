import { CustomValues, displayCustomValue, ProblemTable, DistributorCCRule } from '@/lib/problemTables';
import { api } from '@/lib/api';

export type ProblemTypePrompt = {column: string; choice: string; message: string};

export type CustomerEmailContext = {
  table?: ProblemTable | null;
  problemTypePrompts?: ProblemTypePrompt[];
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

/** Case-insensitive Distributor name matching; * and ? work in wildcard mode. */
export function distributorNameMatches(value: string, rule: DistributorCCRule): boolean {
  const name = value.trim().toLocaleLowerCase();
  const pattern = (rule.pattern || '').trim().toLocaleLowerCase();
  if (!name || !pattern) return false;
  switch (rule.match_type) {
    case 'exact': return name === pattern;
    case 'contains': return name.includes(pattern);
    case 'starts_with': return name.startsWith(pattern);
    case 'ends_with': return name.endsWith(pattern);
    case 'wildcard': {
      const escaped = Array.from(pattern, ch => ch === '*' ? '.*' : ch === '?' ? '.' : ('\\^$+?.()|{}[]'.includes(ch) ? '\\' + ch : ch)).join('');
      const regex = '^' + escaped + '$';
      return new RegExp(regex, 'u').test(name);
    }
    default: return false;
  }
}

/** Combine all matching Distributor-column rules; never add the To contact again in CC. */
export function findDistributorCCRecipients(table: ProblemTable | null | undefined, values: CustomValues, to: string[] = []): string[] {
  const exclude = new Set(to.map(email => email.trim().toLowerCase()));
  const recipients: string[] = [];
  for (const column of table?.columns || []) {
    if (column.column_type !== 'distributor') continue;
    const name = String(values[column.field_key] ?? column.default_value ?? '');
    for (const rule of column.distributor_cc_rules || []) {
      if (!distributorNameMatches(name, rule)) continue;
      for (const raw of rule.cc_emails || []) {
        const address = raw.trim();
        if (address && !exclude.has(address.toLowerCase())) {
          recipients.push(address);
          exclude.add(address.toLowerCase());
        }
      }
    }
  }
  return recipients;
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

{{problem_type_questions}}

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
  const toRecipients = normalizeEmails([...recipientList, ...additionalTo]);
  const ccRecipients = normalizeEmails([
    ...normalizeEmails(context.cc || []),
    ...findDistributorCCRecipients(context.table, context.values || {}, toRecipients),
  ]).filter(address => !toRecipients.some(to => to.toLowerCase() === address.toLowerCase()));
  const multipleCustomerContacts = recipientList.length > 1;

  const problemNumber = context.problemNumber == null || context.problemNumber === ''
    ? ''
    : String(context.problemNumber);

  const allDetails = allProblemDetails(context);
  const includedDetails = customerNotificationDetails(context);

  const configuredProblemType = context.table?.columns.find(column => column.column_type === 'problem_type');
  const problemType = (configuredProblemType
    ? allDetails.find(detail => detail.fieldKey === configuredProblemType.field_key)
    : undefined) || findDetail(allDetails, ['Problem Type', 'ProblemType']);
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
  const questionPrompts = (context.problemTypePrompts || []).filter(prompt =>
    typeof prompt?.message === 'string' && prompt.message.trim(),
  );
  const problemTypeQuestions = questionPrompts.length
    ? ['Information requested from the customer:', ...questionPrompts.map(prompt =>
      `${prompt.column}: ${prompt.choice}\n${prompt.message.trim()}`)].join('\n\n')
    : '';

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
  // Honor the configured expiration period. The standard 30-day notification
  // matches the wording requested for customer emails exactly.
  const automaticDisposalNotice = expirationDays === 0
    ? 'Please note: the sample(s) in this ticket will be up for disposal if no action is received today.'
    : `Please note: the sample(s) in this ticket will be up for disposal if no action is received in ${expirationDays} ${expirationDays === 1 ? 'day' : 'days'}.`;

  const multipleContactsNotice = multipleCustomerContacts
    ? 'This notification is being sent to multiple contacts because a primary contact for the sample(s) could not be confirmed from our records. If another person in your organization should handle this matter, please forward this message to them or let ALS Customer Service know.'
    : '';

  const values: Record<string, string> = {
    na_edm_email: context.edmontonRecipient || 'NAEDM.DE@ALSGlobal.com',
    problem_id: problemNumber,
    problem_type: subjectType,
    als_sample_tracking_number: sampleTracking?.value || 'Not provided',
    reason_for_hold: reasonForHold?.value || 'Please contact ALS Customer Service for details',
    date_received: dateReceived?.value || 'Not provided',
    problem_details: problemDetailLines.join('\n'),
    problem_type_questions: problemTypeQuestions,
    additional_information: additionalInformation,
    multiple_contacts_notice: multipleContactsNotice,
    tracking_link: context.trackingUrl || '',
    automatic_disposal_notice: automaticDisposalNotice,
  };

  const subject = renderTemplate(template.subject_template, values);
  // Older/custom templates may not have the new placeholder. Insert the
  // questions near ticket details or the tracking link instead of after
  // the email signature; fall back to an appended section if neither exists.
  let bodyTemplate = template.body_template;
  if (problemTypeQuestions && !/{{\s*problem_type_questions\s*}}/.test(bodyTemplate)) {
    if (/{{\s*problem_details\s*}}/.test(bodyTemplate)) {
      bodyTemplate = bodyTemplate.replace(/{{\s*problem_details\s*}}/, '{{problem_details}}\n\n{{problem_type_questions}}');
    } else if (/{{\s*tracking_link\s*}}/.test(bodyTemplate)) {
      bodyTemplate = bodyTemplate.replace(/{{\s*tracking_link\s*}}/, '{{problem_type_questions}}\n\n{{tracking_link}}');
    } else {
      bodyTemplate += '\n\n{{problem_type_questions}}';
    }
  }
  const body = renderTemplate(bodyTemplate, values);
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
