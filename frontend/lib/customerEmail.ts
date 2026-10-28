import { CustomValues, displayCustomValue, ProblemTable, BrandCCRule } from '@/lib/problemTables';
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
    .filter(detail => detail.value.trim() !== '' && detail.value !== '—')
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

/** Case-insensitive Brand name matching; * and ? work in wildcard mode. */
export function brandNameMatches(value: string, rule: BrandCCRule): boolean {
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

/** Synchronous direct-Brand fallback; company Brands come from server-resolved CC. */
export function findBrandCCRecipients(table: ProblemTable | null | undefined, values: CustomValues, to: string[] = []): string[] {
  const exclude = new Set(to.map(email => email.trim().toLowerCase()));
  const recipients: string[] = [];
  for (const column of table?.columns || []) {
    if (column.column_type !== 'brand') continue;
    const brand = String(values[column.field_key] ?? '');
    for (const rule of column.brand_cc_rules || []) {
      if (rule.pending_brand_review || !(rule.sources || ['ticket']).includes('ticket') || !brandNameMatches(brand, rule)) continue;
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
{{sample_initial_information}}

{{tracking_link}}

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
  // Brand CC rules apply only when preparing a tracking-link email (new or
  // resent). Ordinary correspondence must never acquire automatic Brand CC.
  const ccRecipients = normalizeEmails([
    ...normalizeEmails(context.cc || []),
    ...(context.trackingUrl ? findBrandCCRecipients(context.table, context.values || {}, toRecipients) : []),
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
    // Only fields explicitly marked 'Include in customer email' are shown.
    // Empty fields are already filtered out and the order follows table columns.
    sample_initial_information: includedDetails.map(detail => `${detail.label}: ${detail.value}`).join('\n'),
    // Backwards compatibility for saved templates that still reference this
    // old token: Problem Type instructions belong in the customer chat only.
    problem_type_questions: '',
    additional_information: additionalInformation,
    multiple_contacts_notice: multipleContactsNotice,
    tracking_link: context.trackingUrl || '',
    automatic_disposal_notice: automaticDisposalNotice,
  };

  const subject = renderTemplate(template.subject_template, values);
  // Never inject Problem Type customer-chat questions into tracking emails.
  // Legacy templates containing {{problem_type_questions}} render it empty.
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

// Keep handler URLs short: browser protocol-handler redirects can also reject
// excessively long mailto URLs. This is a conservative limit, not a standard.
export const OUTLOOK_WEB_COMPOSE_URL_LIMIT = 1500;
export const OUTLOOK_EMAIL_FALLBACK_EVENT = 'als-outlook-email-manual-compose';

export type OutlookWebDraft = CustomerEmailContent & {
  link: string;
  mailtoLink: string;
  fullLinkLength: number;
  manualBody: boolean;
  headersPrefilled: boolean;
};

/**
 * Prefer mailto so the user's configured email handler (Outlook on the web)
 * can receive To, Cc, Subject and Body. A normal website cannot register
 * Outlook as the handler on the user's behalf. The browser must be configured.
 */
export function outlookWebDraftForMailto(mailto: string): OutlookWebDraft {
  const source = new URL(mailto);
  if (source.protocol !== 'mailto:') throw new Error('Expected an email draft link.');
  const to = decodeURIComponent(source.pathname).split(',').map(value => value.trim()).filter(Boolean);
  const cc = (source.searchParams.get('cc') || '').split(',').map(value => value.trim()).filter(Boolean);
  const subject = source.searchParams.get('subject') || '';
  const body = source.searchParams.get('body') || '';

  // Only remove fields from the LAUNCHED link when the full link exceeds
  // the threshold. The dialog always retains every field for manual copying.
  const compactLink = (includeCc: boolean, includeSubject: boolean, includeBody: boolean) => {
    const query: string[] = [];
    if (includeCc && cc.length) query.push(`cc=${encodeURIComponent(cc.join(','))}`);
    if (includeSubject && subject) query.push(`subject=${encodeURIComponent(subject)}`);
    if (includeBody && body) query.push(`body=${encodeURIComponent(body)}`);
    return `mailto:${to.join(',')}${query.length ? `?${query.join('&')}` : ''}`;
  };
  let link = mailto;
  const manualBody = mailto.length > OUTLOOK_WEB_COMPOSE_URL_LIMIT;
  let headersPrefilled = true;
  if (manualBody) {
    link = compactLink(true, true, false);
    if (link.length > OUTLOOK_WEB_COMPOSE_URL_LIMIT) {
      headersPrefilled = false;
      link = compactLink(true, false, false);
    }
    if (link.length > OUTLOOK_WEB_COMPOSE_URL_LIMIT) link = compactLink(false, false, false);
    if (link.length > OUTLOOK_WEB_COMPOSE_URL_LIMIT) link = 'mailto:';
  }
  return {
    to, cc, subject, body,
    mailtoLink: mailto,
    link,
    fullLinkLength: mailto.length,
    manualBody,
    headersPrefilled,
  };
}

/** Launch the registered mailto handler directly from the Send Email click.
 * Longer drafts launch with safe-length fields and expose their omitted content
 * in a non-blocking copy notice. Never open a second modal for a normal draft.
 */
export function invokeCustomerEmail(mailto: string): void {
  const draft = outlookWebDraftForMailto(mailto);
  const link = document.createElement('a');
  link.href = draft.link;
  link.style.display = 'none';
  document.body.appendChild(link);
  try {
    link.click();
  } finally {
    link.remove();
  }
  // This event is used ONLY to display missing content for oversized mailto
  // URLs. Short drafts reset any old warning and show nothing additional.
  window.dispatchEvent(new CustomEvent<OutlookWebDraft>(OUTLOOK_EMAIL_FALLBACK_EVENT, { detail: draft }));
}
