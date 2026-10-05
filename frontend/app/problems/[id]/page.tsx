'use client';

import { useEffect, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { applyIntercolumnRules, automaticDisposalDisplay, CustomValues, displayCustomValue, ProblemTable } from '@/lib/problemTables';
import DynamicField from '@/components/DynamicField';
import { CustomerEmailContent, CustomerEmailContext, findCustomerEmails, invokeCustomerEmail, mailtoForCustomerEmail, prepareCustomerEmail } from '@/lib/customerEmail';
import CustomerEmailModal from '@/components/CustomerEmailModal';
import GeneralCustomerEmailModal from '@/components/GeneralCustomerEmailModal';
import BackToTestingEmailModal, { TestingEmailDetails } from '@/components/BackToTestingEmailModal';
import { changeReasonHeaders } from '@/lib/changeReason';
import { useChangeReasonModal } from '@/components/ChangeReasonModal';
import { useCurrentUser } from '@/components/CurrentUserContext';
import CameraCapture from '@/components/CameraCapture';
import StaffImage from '@/components/StaffImage';
import StaffAttachmentLink from '@/components/StaffAttachmentLink';
import MentionTextarea from '@/components/MentionTextarea';
import MentionText from '@/components/MentionText';
import MentionEmailModal, { MentionEmailDraft } from '@/components/MentionEmailModal';
import CustomerHistoryReplyEmailModal, { CustomerHistoryReplyEmail } from '@/components/CustomerHistoryReplyEmailModal';

type Comment = { id: number; body: string; author_email: string; author_username: string; author_name: string; legacy_author: string; mentions?: { id:number; username:string; name:string }[]; created_at: string };
type ProblemImage = { id:number; has_image?:boolean; original_name:string; size_bytes:number; include_in_customer_notification:boolean; uploaded_by_email:string; uploaded_at:string };
type ProblemAttachment = { id:number; file:string; original_name:string; content_type:string; size_bytes:number; include_in_customer_notification:boolean; uploaded_by_email:string; uploaded_at:string };
type HistoryEntry = {
  id: number;
  action: 'created' | 'updated' | 'comment' | 'customer_notification' | 'acknowledged';
  action_label: string;
  summary: string;
  details: {
    changes?: { field:string; before:unknown; after:unknown }[];
    comment?: string;
    mentions?: { id:number; username:string; name:string }[];
    reason?: string;
    email_not_sent?: string;
    customer_signature?: string;
    customer_requested_information?: string;
    customer_uploaded_images?: { id:number; name:string; size_bytes:number }[];
    customer_uploaded_attachments?: { id:number; name:string; size_bytes:number; content_type?:string }[];
    replied_to_history_id?: number;
    customer_message?: string;
    staff_reply?: string;
    recipients?: string[];
    tracking_url?: string;
  };
  actor_email: string;
  actor_name: string;
  created_at: string;
};
type Problem = { id: string; problem_number:number; created_at:string; table:string; table_name:string; container_id:string; customer_notified_at:string|null; automatic_disposal_started_at:string|null; expires_at:string|null; expiration_status:'active'|'expired'; days_until_expiration:number|null; days_until_automatic_disposal:number|null; pt_days:number; tracking_url:string; tracking_link_expiry:string|null; back_to_testing_notified_at:string|null; acknowledged_at:string|null; comments: Comment[]; history: HistoryEntry[]; images: ProblemImage[]; attachments: ProblemAttachment[]; custom_values: CustomValues };

type MentionEmailPreview = {
  requires_email: boolean;
  emails: MentionEmailDraft[];
  confirmation_token: string;
};

type CustomerHistoryReplyPreview = {
  email: CustomerHistoryReplyEmail;
  confirmation_token: string;
};

function displayHistoryValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '—';
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function formatBytes(value: number) {
  if (!value) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  const amount = value / (1024 ** index);
  return `${amount >= 10 || index === 0 ? amount.toFixed(0) : amount.toFixed(1)} ${units[index]}`;
}

function historyIcon(action: HistoryEntry['action']) {
  if (action === 'comment') return '💬';
  if (action === 'created') return '＋';
  if (action === 'customer_notification') return '✉';
  if (action === 'acknowledged') return '✓';
  return '✎';
}

export default function Detail() {
  const currentUser = useCurrentUser();
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { requestChangeReason, changeReasonModal } = useChangeReasonModal();
  const [p, setP] = useState<Problem | null>(null);
  const [table, setTable] = useState<ProblemTable | null>(null);
  const [customValues, setCustomValues] = useState<CustomValues>({});
  const [containerCode, setContainerCode] = useState('');
  const [comment, setComment] = useState('');
  const [historyEntryOpen, setHistoryEntryOpen] = useState(false);
  const [preparingMentionEmail, setPreparingMentionEmail] = useState(false);
  const [savingMentionComment, setSavingMentionComment] = useState(false);
  const [mentionEmailDraft, setMentionEmailDraft] = useState<{ body: string; emails: MentionEmailDraft[]; confirmationToken: string } | null>(null);
  const [historyReplyTarget, setHistoryReplyTarget] = useState<HistoryEntry | null>(null);
  const [historyReplyText, setHistoryReplyText] = useState('');
  const [preparingHistoryReply, setPreparingHistoryReply] = useState(false);
  const [savingHistoryReply, setSavingHistoryReply] = useState(false);
  const [historyReplyEmailDraft, setHistoryReplyEmailDraft] = useState<{ historyId:number; reply:string; email:CustomerHistoryReplyEmail; confirmationToken:string; launchedAt:number } | null>(null);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState('');
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [attachmentFiles, setAttachmentFiles] = useState<File[]>([]);
  const [imageInputKey, setImageInputKey] = useState(0);
  const [attachmentInputKey, setAttachmentInputKey] = useState(0);
  const [uploadingImages, setUploadingImages] = useState(false);
  const [uploadingAttachments, setUploadingAttachments] = useState(false);
  const [pendingEmailLaunch, setPendingEmailLaunch] = useState<{ content: CustomerEmailContent; trackingToken: string } | null>(null);
  const [recordingEmailSent, setRecordingEmailSent] = useState(false);
  const [preparingCustomerEmail, setPreparingCustomerEmail] = useState(false);
  const [generalEmailOpen, setGeneralEmailOpen] = useState(false);
  const [recordingGeneralEmail, setRecordingGeneralEmail] = useState(false);
  const [revokingTrackingLink, setRevokingTrackingLink] = useState(false);
  const [testingEmailDraft, setTestingEmailDraft] = useState<{
    mode: 'transition' | 'notify'; values: CustomValues; containerCode: string; reason: string;
  } | null>(null);
  const [testingEmailBusy, setTestingEmailBusy] = useState(false);
  const [testingEmailError, setTestingEmailError] = useState('');
  const [deleteConfirmationOpen, setDeleteConfirmationOpen] = useState(false);
  const [deletingProblem, setDeletingProblem] = useState(false);
  const initialHashHandled = useRef(false);

  async function load() {
    try {
      const problem: Problem = await api(`/problem-samples/${id}/`);
      setP(problem); setCustomValues(problem.custom_values || {}); setContainerCode(problem.container_id || '');
      if (problem.table) setTable(await api(`/problem-tables/${problem.table}/`));
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed'); }
  }
  useEffect(() => { load(); }, [id]);
  useEffect(() => {
    if (!p || initialHashHandled.current || typeof window === 'undefined' || !window.location.hash) return;
    const targetId = decodeURIComponent(window.location.hash.slice(1));
    if (!targetId) return;
    initialHashHandled.current = true;
    window.requestAnimationFrame(() => {
      document.getElementById(targetId)?.scrollIntoView({ block: 'start' });
    });
  }, [p]);
  function updateCustomValue(columnId: string, fieldKey: string, value: unknown) {
    if (!table) return;
    setCustomValues(current => {
      const next = { ...current, [fieldKey]: value };
      for (const candidate of table.columns) {
        if (candidate.column_type === 'client_email' && (candidate.client_email_dependencies || []).includes(columnId)) {
          next[candidate.field_key] = '';
        }
      }
      return applyIntercolumnRules(table, next);
    });
  }

  async function saveComment(body: string, confirmationToken = '') {
    setSavingMentionComment(true);
    setError('');
    try {
      await api(`/problem-samples/${id}/comments/`, {
        method: 'POST',
        body: JSON.stringify({
          body,
          ...(confirmationToken ? { mention_email_confirmation_token: confirmationToken } : {}),
        }),
        successMessage:'History entry added successfully.',
        errorMessage:'Could not add history entry',
      });
      setComment('');
      setHistoryEntryOpen(false);
      setMentionEmailDraft(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add history entry');
      throw e;
    } finally {
      setSavingMentionComment(false);
    }
  }

  async function add() {
    const body = comment.trim();
    if (!body || preparingMentionEmail || savingMentionComment) return;
    setPreparingMentionEmail(true);
    setError('');
    try {
      const preview: MentionEmailPreview = await api(`/problem-samples/${id}/prepare-comment-mentions/`, {
        method: 'POST',
        body: JSON.stringify({ body }),
        errorMessage: 'Could not prepare mention email',
      });
      if (preview.requires_email && preview.emails.length) {
        setMentionEmailDraft({ body, emails: preview.emails, confirmationToken: preview.confirmation_token });
      } else {
        await saveComment(body);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to prepare comment');
    } finally {
      setPreparingMentionEmail(false);
    }
  }
  function openHistoryReply(entry: HistoryEntry) {
    setError('');
    setHistoryReplyTarget(entry);
    setHistoryReplyText('');
  }

  async function prepareHistoryReply() {
    if (!historyReplyTarget || preparingHistoryReply || savingHistoryReply) return;
    const reply = historyReplyText.trim();
    if (!reply) return;
    setPreparingHistoryReply(true);
    setError('');
    try {
      const preview: CustomerHistoryReplyPreview = await api(`/problem-samples/${id}/prepare-customer-history-reply/`, {
        method: 'POST',
        body: JSON.stringify({ history_id: historyReplyTarget.id, reply }),
        errorMessage: 'Could not prepare customer reply email',
      });
      const launchedAt = Date.now();
      // Submit immediately attempts to open the generated message in the staff
      // member's configured email application. The preview remains available
      // so they can retry if the browser/OS blocks the first launch.
      invokeCustomerEmail(mailtoForCustomerEmail({
        to: preview.email.to, cc: preview.email.cc || [], subject: preview.email.subject, body: preview.email.body,
      }));
      setHistoryReplyEmailDraft({
        historyId: historyReplyTarget.id,
        reply,
        email: preview.email,
        confirmationToken: preview.confirmation_token,
        launchedAt,
      });
      setHistoryReplyTarget(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not prepare customer reply email');
    } finally {
      setPreparingHistoryReply(false);
    }
  }

  async function confirmHistoryReplySent() {
    if (!historyReplyEmailDraft || savingHistoryReply) return;
    setSavingHistoryReply(true);
    setError('');
    try {
      await api(`/problem-samples/${id}/customer-history-reply-sent/`, {
        method: 'POST',
        body: JSON.stringify({
          history_id: historyReplyEmailDraft.historyId,
          reply: historyReplyEmailDraft.reply,
          confirmation_token: historyReplyEmailDraft.confirmationToken,
        }),
        successMessage: 'Customer reply recorded.',
        errorMessage: 'Could not save customer reply',
      });
      setHistoryReplyEmailDraft(null);
      setHistoryReplyText('');
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save customer reply');
    } finally {
      setSavingHistoryReply(false);
    }
  }

  async function saveCustom() {
    setSaved(''); setError('');
    const requestedContainer = containerCode.trim();
    const reason = await requestChangeReason('Why are you changing this ticket?');
    if (reason === null) return;
    if (p && p.custom_values?.['current-workflow'] !== 'Back to testing' && customValues['current-workflow'] === 'Back to testing') {
      setTestingEmailError('');
      setTestingEmailDraft({ mode: 'transition', values: { ...customValues }, containerCode: requestedContainer, reason });
      return;
    }
    try {
      const updated = await api(`/problem-samples/${id}/`, {
        method:'PATCH',
        headers: changeReasonHeaders(reason),
        body:JSON.stringify({custom_values:customValues, container_code:requestedContainer}),
        successMessage:'Ticket saved successfully.',
        errorMessage:'Could not save ticket',
      });
      setP(updated);
      setCustomValues(updated.custom_values || {});
      setContainerCode(updated.container_id || '');
      setSaved('Ticket saved.');
      await load();
    }
    catch(e) { setError(e instanceof Error ? e.message : 'Failed to save'); }
  }
  async function uploadImages() {
    if (!imageFiles.length || !p) return;
    setUploadingImages(true); setError('');
    try {
      const created: ProblemImage[] = [];
      for (const file of imageFiles) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('include_in_customer_notification', 'false');
        created.push(await api(`/problem-samples/${id}/images/`, { method:'POST', body:formData, errorMessage:`Could not upload image ${file.name}` }));
      }
      setP(current => current ? { ...current, images:[...(current.images || []), ...created] } : current);
      setImageFiles([]); setImageInputKey(key => key + 1);
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to upload image'); }
    finally { setUploadingImages(false); }
  }

  async function uploadCapturedImage(file: File) {
    if (!p || uploadingImages) return;
    setUploadingImages(true); setError('');
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('include_in_customer_notification', 'false');
      const created: ProblemImage = await api(`/problem-samples/${id}/images/`, { method:'POST', body:formData, successMessage:'Photo added to ticket.', errorMessage:'Could not upload captured photo' });
      setP(current => current ? { ...current, images:[...(current.images || []), created] } : current);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to upload captured photo');
      throw e;
    } finally {
      setUploadingImages(false);
    }
  }

  async function uploadAttachments() {
    if (!attachmentFiles.length || !p) return;
    setUploadingAttachments(true); setError('');
    try {
      const created: ProblemAttachment[] = [];
      for (const file of attachmentFiles) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('include_in_customer_notification', 'false');
        created.push(await api(`/problem-samples/${id}/attachments/`, { method:'POST', body:formData, errorMessage:`Could not upload attachment ${file.name}` }));
      }
      setP(current => current ? { ...current, attachments:[...(current.attachments || []), ...created] } : current);
      setAttachmentFiles([]); setAttachmentInputKey(key => key + 1);
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to upload attachment'); }
    finally { setUploadingAttachments(false); }
  }

  async function removeImage(image: ProblemImage) {
    if (!window.confirm(`Delete image “${image.original_name || 'image'}”?`)) return;
    try {
      await api(`/problem-samples/${id}/images/${image.id}/`, { method:'DELETE', successMessage:'Image deleted.', errorMessage:'Could not delete image' });
      setP(current => current ? { ...current, images:(current.images || []).filter(item => item.id !== image.id) } : current);
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to delete image'); }
  }

  async function removeAttachment(attachment: ProblemAttachment) {
    if (!window.confirm(`Delete attachment “${attachment.original_name}”?`)) return;
    try {
      await api(`/problem-samples/${id}/attachments/${attachment.id}/`, { method:'DELETE', successMessage:'Attachment deleted.', errorMessage:'Could not delete attachment' });
      setP(current => current ? { ...current, attachments:(current.attachments || []).filter(item => item.id !== attachment.id) } : current);
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to delete attachment'); }
  }

  async function deleteProblemSample() {
    if (!p || deletingProblem) return;
    setDeletingProblem(true); setError('');
    try {
      const destinationTable = table?.id || p.table || '';
      await api(`/problem-samples/${id}/`, {
        method:'DELETE',
        successMessage:`Ticket #${p.problem_number} deleted successfully.`,
        errorMessage:'Could not delete ticket',
      });
      setDeleteConfirmationOpen(false);
      router.push(destinationTable ? `/problem-samples?table=${encodeURIComponent(destinationTable)}` : '/dashboard');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete ticket');
      setDeletingProblem(false);
    }
  }

  if (error && !p) return <div className="card error">{error}</div>;
  if (!p) return <div>Loading…</div>;

  const problem = p;
  const customerEmails = findCustomerEmails(table, customValues);
  const rowTitle = `Ticket #${problem.problem_number}`;

  async function sendTrackingLink() {
    if (!customerEmails.length || preparingCustomerEmail) return;
    setError('');
    setPreparingCustomerEmail(true);
    try {
      const credentials = await api(`/problem-samples/${problem.id}/customer-notification-credentials/`, {
        method: 'POST',
        errorMessage: 'Could not prepare ticket tracking link',
      });
      const emailContext: CustomerEmailContext = {
        table,
        values: customValues,
        problemNumber: problem.problem_number,
        tableName: problem.table_name,
        trackingUrl: credentials.tracking_url,
      };
      const draft = await prepareCustomerEmail(customerEmails, emailContext);
      setPendingEmailLaunch({ content: draft.content, trackingToken: credentials.tracking_token });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not prepare tracking-link email');
    } finally {
      setPreparingCustomerEmail(false);
    }
  }

  async function confirmGeneralEmailSent(message: CustomerEmailContent) {
    if (recordingGeneralEmail) return;
    setRecordingGeneralEmail(true); setError('');
    try {
      await api(`/problem-samples/${id}/customer-message-sent/`, {
        method: 'POST', body: JSON.stringify(message),
        successMessage: 'Customer email recorded.', errorMessage: 'Could not record customer email',
      });
      setGeneralEmailOpen(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not record customer email');
    } finally { setRecordingGeneralEmail(false); }
  }

  async function revokeTrackingLink() {
    if (!p?.tracking_url || revokingTrackingLink) return;
    if (!window.confirm('Revoke this tracking link? The customer will lose access immediately. The old URL cannot be restored; you can send a new link later. Automatic disposal settings and the countdown will remain unchanged.')) return;
    const reason = await requestChangeReason('Why are you revoking this tracking link?');
    if (reason === null) return;
    setRevokingTrackingLink(true); setError('');
    try {
      await api(`/problem-samples/${id}/revoke-tracking-link/`, {
        method: 'POST', headers: changeReasonHeaders(reason),
        successMessage: 'Tracking link revoked.', errorMessage: 'Could not revoke tracking link',
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not revoke tracking link');
    } finally { setRevokingTrackingLink(false); }
  }

  function dismissEmailLaunch() {
    if (preparingCustomerEmail || recordingEmailSent) return;
    setPendingEmailLaunch(null);
    setError('');
  }

  async function recordCustomerEmailNotSent(reason: string) {
    if (!pendingEmailLaunch || recordingEmailSent) return;
    setRecordingEmailSent(true); setError('');
    try {
      await api(`/problem-samples/${id}/email-not-sent/`, {
        method: 'POST',
        body: JSON.stringify({ kind: 'customer', reason }),
        successMessage: 'Reason for not sending the tracking-link email recorded.',
        errorMessage: 'Could not record why the email was not sent',
      });
      setPendingEmailLaunch(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not record why the email was not sent');
    } finally { setRecordingEmailSent(false); }
  }

  async function confirmEmailSent() {
    if (!pendingEmailLaunch || recordingEmailSent) return;
    setError('');
    setRecordingEmailSent(true);
    try {
      await api(`/problem-samples/${id}/customer-notification-sent/`, {
        method:'POST',
        body:JSON.stringify({
          delivery_method: 'mailto',
          tracking_token: pendingEmailLaunch.trackingToken,
        }),
        successMessage:'Tracking link sent. The automatic-disposal countdown has started when applicable.',
        errorMessage:'Could not record tracking-link email',
      });
      setPendingEmailLaunch(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not record tracking-link email');
    } finally {
      setRecordingEmailSent(false);
    }
  }

  function testingDetails(): TestingEmailDetails {
    const values = testingEmailDraft?.values || p?.custom_values || {};
    const valueFor = (keys: string[]) => {
      const column = table?.columns.find(item => keys.includes(item.field_key) || keys.includes(item.name.toLowerCase().replace(/[^a-z0-9]+/g, '-')));
      return String((column && values[column.field_key]) || '').trim();
    };
    const customerMessages = (p?.history || [])
      .filter(entry => typeof entry.details?.customer_requested_information === 'string' && entry.details.customer_requested_information.trim())
      .slice()
      .reverse()
      .map(entry => ({
        message: entry.details.customer_requested_information!.trim(),
        signature: String(entry.details.customer_signature || '').trim(),
        createdAt: entry.created_at,
      }));
    return {
      problemNumber: p?.problem_number || 0, tableName: p?.table_name || '',
      containerId: testingEmailDraft?.containerCode || p?.container_id || '',
      trackingNumber: valueFor(['als-sample-tracking-number', 'als-tracking-number', 'sample-tracking-number']) || String(values['als-tracking-number'] || ''),
      problemType: valueFor(['problem-type']),
      reasonForHold: valueFor(['reason-for-hold', 'issue-description']),
      customerMessages,
      ticketUrl: typeof window !== 'undefined' ? `${window.location.origin}/problems/${p?.id || id}` : `/problems/${p?.id || id}`,
    };
  }

  async function finishTestingEmail(sent: boolean, body: string, recipient: string, notSentReason?: string) {
    if (!testingEmailDraft || testingEmailBusy) return;
    setTestingEmailBusy(true); setTestingEmailError('');
    try {
      if (testingEmailDraft.mode === 'transition') {
        await api(`/problem-samples/${id}/`, {
          method: 'PATCH', headers: changeReasonHeaders(testingEmailDraft.reason),
          body: JSON.stringify({ custom_values: testingEmailDraft.values, container_code: testingEmailDraft.containerCode,
            back_to_testing_email_sent: sent, back_to_testing_email_body: sent ? body : '', email_recipient: recipient,
            ...(!sent ? { back_to_testing_not_sent_reason: notSentReason } : {}) }),
          successMessage: sent ? 'Workflow updated and NA.EDM notification recorded.' : 'Workflow updated. NA.EDM still needs to be notified.',
          errorMessage: 'Could not update ticket',
        });
      } else if (sent) {
        await api(`/problem-samples/${id}/back-to-testing-notification/`, {
          method: 'POST', body: JSON.stringify({ email_body: body, email_recipient: recipient }),
          successMessage: 'NA.EDM notification recorded.', errorMessage: 'Could not record notification',
        });
      } else {
        await api(`/problem-samples/${id}/email-not-sent/`, {
          method: 'POST', body: JSON.stringify({ kind: 'back_to_testing', reason: notSentReason }),
          successMessage: 'Reason for not sending the NA.EDM email recorded.',
          errorMessage: 'Could not record why the email was not sent',
        });
      }
      setTestingEmailDraft(null);
      setSaved(sent ? 'NA.EDM notification recorded.' : 'NA.EDM still needs to be notified.');
      await load();
    } catch (e) {
      setTestingEmailError(e instanceof Error ? e.message : 'Could not save email confirmation.');
    } finally { setTestingEmailBusy(false); }
  }

  return <div>
    <div className="row" style={{marginBottom:14}}>
      <div style={{marginRight:'auto'}}><div className="eyebrow">{p.table_name || 'Tickets'}</div><h1 className="page-heading" style={{marginBottom:0}}>{rowTitle}</h1></div>
      {currentUser?.is_admin && table && <Link className="button secondary" href={`/tables/${table.id}`}>Manage Columns</Link>}
      <button
        type="button"
        className="button"
        onClick={sendTrackingLink}
        disabled={!customerEmails.length || preparingCustomerEmail}
        title={!customerEmails.length ? 'No customer email is available to receive the tracking link.' : undefined}
      >
        {preparingCustomerEmail ? 'Preparing…' : 'Send Tracking Link'}
      </button>
      <button type="button" className="button secondary" onClick={() => setGeneralEmailOpen(true)} disabled={!customerEmails.length} title={!customerEmails.length ? 'No customer email is available for this ticket.' : undefined}>Email Customer</button>
      {p.tracking_url && <button type="button" className="button danger" onClick={revokeTrackingLink} disabled={revokingTrackingLink}>{revokingTrackingLink ? 'Revoking…' : 'Revoke Tracking Link'}</button>}
      <button type="button" className="button danger" onClick={() => setDeleteConfirmationOpen(true)}>Delete Row</button>
    </div>
    {error && <div className="card error" style={{marginBottom:14}}>{error}</div>}
    {saved && <div className="card success" style={{marginBottom:14}}>{saved}</div>}
    {p.custom_values?.['current-workflow'] === 'Back to testing' && !p.back_to_testing_notified_at && <section className="card" style={{marginBottom:14, padding:16}}>
      <strong>NA.EDM needs to be notified.</strong> Send the Back to Testing email from your company email account.
      <button type="button" className="button" style={{marginLeft:12}} onClick={() => { setTestingEmailError(''); setTestingEmailDraft({ mode:'notify', values:p.custom_values, containerCode:p.container_id || '', reason:'' }); }}>Notify NA.EDM</button>
    </section>}

    <section className={`sample-expiration-banner sample-expiration-${p.expiration_status}`} style={{marginBottom:14}}>
      <div>
        <div className="sample-expiration-title">
          <span>Container {p.container_id || 'Unassigned'}</span>
          {p.expiration_status === 'expired' ? <span className="badge expiration-expired">Expired</span> : <span className="badge expiration-active">{p.days_until_expiration ?? '—'} day{p.days_until_expiration === 1 ? '' : 's'} remaining</span>}
        </div>
        <div className="muted result-meta">Expiration period: {(p.pt_days ?? table?.pt_days ?? 30) === 0 ? 'Immediate' : `${p.pt_days ?? table?.pt_days ?? 30} day${(p.pt_days ?? table?.pt_days ?? 30) === 1 ? '' : 's'}`}. {p.customer_notified_at ? `Tracking link first sent ${new Date(p.customer_notified_at).toLocaleString()}.` : 'Automatic disposal begins when the tracking-link email is first confirmed as sent.'}</div>
      </div>
      <div className="sample-expiration-side">{p.expires_at ? <>Expires<br/><strong>{new Date(p.expires_at).toLocaleString()}</strong></> : 'No expiration date yet'}</div>
    </section>

    <section id="follow-ups" className="panel history-panel" style={{marginBottom:14, scrollMarginTop:24}}>
      <div className="panel-header">
        <strong>History</strong>
        <div className="row" style={{marginLeft:'auto', gap:8}}>
          <span className="history-count">{p.history?.length || 0} activities</span>
          <button type="button" className="button secondary small" onClick={() => { setHistoryEntryOpen(open => !open); setError(''); }} disabled={preparingMentionEmail || savingMentionComment}>{historyEntryOpen ? 'Close' : 'Add History Entry'}</button>
        </div>
      </div>
      <div className="panel-body">
        {historyEntryOpen && <div className="history-entry-composer">
          <div className="field"><label>History entry</label><MentionTextarea value={comment} onChange={setComment} placeholder="Add a history entry…" /></div>
          <div className="row" style={{marginTop:10}}>
            <button className="button" onClick={add} disabled={!comment.trim() || preparingMentionEmail || savingMentionComment}>{preparingMentionEmail ? 'Preparing mention email…' : savingMentionComment ? 'Saving…' : 'Add History Entry'}</button>
            <button type="button" className="button secondary" onClick={() => { setHistoryEntryOpen(false); setComment(''); setError(''); }} disabled={preparingMentionEmail || savingMentionComment}>Cancel</button>
          </div>
        </div>}
        <div className="history-list">
        {!p.history?.length && <div className="muted">No activity has been recorded for this row yet.</div>}
        {(p.history || []).map(entry => {
          const changes = entry.details?.changes || [];
          const actor = entry.actor_name || entry.actor_email || 'Unknown user';
          return <div className="history-item" key={entry.id}>
            <div className={`history-icon history-icon-${entry.action}`}>{historyIcon(entry.action)}</div>
            <div className="history-content">
              <div className="history-heading"><strong>{entry.summary}</strong><span className="history-time">{new Date(entry.created_at).toLocaleString()}</span></div>
              <div className="history-meta">{actor}</div>
              {entry.details?.reason && <div className="history-reason"><strong>Reason:</strong> {entry.details.reason}</div>}
              {entry.details?.customer_signature && <div className="history-signature"><strong>Customer signature:</strong> {entry.details.customer_signature}</div>}
              {entry.details?.customer_requested_information && <div className="history-customer-information">
                <strong>Information provided by customer:</strong><div>{entry.details.customer_requested_information}</div>
                <div style={{marginTop:10}}><button type="button" className="button secondary small" onClick={() => openHistoryReply(entry)}>Reply</button></div>
              </div>}
              {entry.details?.staff_reply && <div className="history-customer-information"><strong>Staff reply:</strong><div>{entry.details.staff_reply}</div>{entry.details.customer_message && <div className="muted" style={{marginTop:6}}><strong>Replying to:</strong> {entry.details.customer_message}</div>}{entry.details.recipients?.length ? <div className="muted" style={{marginTop:4}}>Emailed to {entry.details.recipients.join('; ')}</div> : null}</div>}
              {((entry.details?.customer_uploaded_images?.length || 0) > 0 || (entry.details?.customer_uploaded_attachments?.length || 0) > 0) && <div className="history-customer-files">
                <strong>Files attached by customer</strong>
                {(entry.details?.customer_uploaded_images?.length || 0) > 0 && <div className="history-customer-image-grid">
                  {(entry.details.customer_uploaded_images || []).map(image => <div className="history-customer-image" key={`history-image-${entry.id}-${image.id}`}>
                    <StaffImage problemId={p.id} imageId={image.id} className="history-customer-image-preview" alt={image.name || 'Customer image'} openInNewTab />
                    <div className="history-customer-file-copy"><span className="history-customer-file-name">{image.name || 'Customer image'}</span><span className="history-customer-file-meta">Image · {formatBytes(image.size_bytes)}</span></div>
                  </div>)}
                </div>}
                {(entry.details?.customer_uploaded_attachments?.length || 0) > 0 && <div className="history-customer-attachment-list">
                  {(entry.details.customer_uploaded_attachments || []).map(attachment => <div className="history-customer-attachment" key={`history-attachment-${entry.id}-${attachment.id}`}>
                    <div className="history-customer-file-copy"><span className="history-customer-file-name">{attachment.name || 'Customer attachment'}</span><span className="history-customer-file-meta">{formatBytes(attachment.size_bytes)}{attachment.content_type ? ` · ${attachment.content_type}` : ''}</span></div>
                    <StaffAttachmentLink problemId={p.id} attachmentId={attachment.id} filename={attachment.name || `attachment-${attachment.id}`} className="button secondary small">Download</StaffAttachmentLink>
                  </div>)}
                </div>}
              </div>}
              {entry.action === 'comment' && entry.details?.comment && <div className="history-comment"><MentionText text={entry.details.comment} /></div>}
              {(entry.action === 'updated' || entry.action === 'customer_notification' || entry.action === 'acknowledged') && changes.length > 0 && <div className="history-changes">
                {changes.map((change, index) => <div className="history-change" key={`${entry.id}-${index}`}>
                  <span className="history-field">{change.field}</span>
                  <span className="history-before">{displayHistoryValue(change.before)}</span>
                  <span className="history-arrow">→</span>
                  <span className="history-after">{displayHistoryValue(change.after)}</span>
                </div>)}
              </div>}
              {entry.action === 'updated' && changes.length === 0 && !entry.details?.email_not_sent && <div className="muted history-no-change">No field values changed.</div>}
            </div>
          </div>;
        })}
        </div>
      </div>
    </section>

    <div className="two-col">
      <div className="stack">
        <section className="panel panel-blue"><div className="panel-header">Ticket</div><div className="panel-body stack">
          {table ? <><div className="grid"><div className="field readonly-field"><label>Ticket ID</label><input className="input readonly-input" value={p.problem_number} disabled readOnly aria-disabled="true" /></div><div className="field readonly-field"><label>Date Created</label><input className="input readonly-input" value={p.created_at ? new Date(p.created_at).toLocaleString() : '—'} disabled readOnly aria-disabled="true" /></div><div className="field"><label htmlFor="edit-container-id">Container ID</label><input id="edit-container-id" className="input" value={containerCode} onChange={event=>setContainerCode(event.target.value)} placeholder="e.g. PC-000123" /><div className="muted result-meta">Enter an active Container ID to assign this ticket, or clear the field to remove it from its container.</div></div>{table.columns.filter(c => !c.is_system || ['current-workflow', 'dispose-automatically', 'system-days-until-automatic-disposal', 'system-tracking-link', 'system-tracking-link-expiry'].includes(c.field_key)).map(column => column.field_key === 'system-days-until-automatic-disposal'
            ? <div className="field readonly-field" key={column.id}><label>{column.name}</label><input className="input readonly-input" value={automaticDisposalDisplay({...p, custom_values: customValues})} disabled readOnly aria-disabled="true" /></div>
            : column.field_key === 'system-tracking-link'
              ? <div className="field readonly-field tracking-link-field" key={column.id}><label>{column.name}</label>{p.tracking_url ? <a className="table-link tracking-link-value" href={p.tracking_url} target="_blank" rel="noreferrer">{p.tracking_url}</a> : <input className="input readonly-input" value="—" disabled readOnly aria-disabled="true" />}</div>
              : column.field_key === 'system-tracking-link-expiry'
                ? <div className="field readonly-field" key={column.id}><label>{column.name}</label><input className="input readonly-input" value={p.tracking_link_expiry ? new Date(p.tracking_link_expiry).toLocaleString() : (p.tracking_url ? 'Does not expire' : '—')} disabled readOnly aria-disabled="true" /></div>
                : <DynamicField key={column.id} column={column} value={customValues[column.field_key]} allValues={customValues} onChange={value=>updateCustomValue(column.id, column.field_key, value)}/>)}</div><div><button className="button" onClick={saveCustom}>Save Changes</button></div></> : null}
        </div></section>

        <section className="panel file-panel">
          <div className="panel-header"><strong>Images & Attachments</strong><span className="file-count-badge">{(p.images?.length || 0) + (p.attachments?.length || 0)} files</span></div>
          <div className="panel-body stack">
            <div className="muted file-notification-note">Images and attachments are stored with the ticket. Customer emails are opened in your email application without attaching these files.</div>
            <div className="file-subsection">
              <div className="file-subsection-heading"><strong>Images</strong><span className="muted">{p.images?.length || 0}</span></div>
              {(p.images || []).length > 0 && <div className="image-gallery">
                {(p.images || []).map(image => <article className="image-card" key={image.id}>
                  <div className="image-preview-link"><StaffImage problemId={p.id} imageId={image.id} className="image-preview" alt={image.original_name || 'Ticket image'} openInNewTab /></div>
                  <div className="image-card-copy"><div className="file-name">{image.original_name || 'Image'}</div><div className="file-meta">{formatBytes(image.size_bytes)} · {new Date(image.uploaded_at).toLocaleString()}</div></div>
                  <button type="button" className="file-delete" onClick={() => removeImage(image)}>Delete</button>
                </article>)}
              </div>}
              {(p.images || []).length === 0 && <div className="muted file-empty">No images added.</div>}
              <div className="file-upload-row">
                <input key={imageInputKey} className="file-control" type="file" accept="image/jpeg,image/png,image/gif,image/webp" multiple onChange={event => setImageFiles(Array.from(event.target.files || []))} />
                <button type="button" className="button secondary" disabled={!imageFiles.length || uploadingImages} onClick={uploadImages}>{uploadingImages ? 'Uploading…' : `Add Image${imageFiles.length === 1 ? '' : 's'}`}</button>
                <CameraCapture onCapture={uploadCapturedImage} disabled={uploadingImages} />
              </div>
              <div className="muted file-help">Upload JPEG, PNG, GIF, or WebP, or take a photo directly with this device · maximum 25 MB each</div>
            </div>

            <div className="file-subsection">
              <div className="file-subsection-heading"><strong>Attachments</strong><span className="muted">{p.attachments?.length || 0}</span></div>
              {(p.attachments || []).length > 0 && <div className="attachment-list">
                {(p.attachments || []).map(attachment => <article className="attachment-item" key={attachment.id}>
                  <div className="attachment-icon">↧</div>
                  <div className="attachment-copy"><a className="attachment-link" href={attachment.file} target="_blank" rel="noreferrer">{attachment.original_name}</a><div className="file-meta">{formatBytes(attachment.size_bytes)}{attachment.content_type ? ` · ${attachment.content_type}` : ''} · {new Date(attachment.uploaded_at).toLocaleString()}</div></div>
                  <button type="button" className="file-delete" onClick={() => removeAttachment(attachment)}>Delete</button>
                </article>)}
              </div>}
              {(p.attachments || []).length === 0 && <div className="muted file-empty">No attachments added.</div>}
              <div className="file-upload-row">
                <input key={attachmentInputKey} className="file-control" type="file" multiple onChange={event => setAttachmentFiles(Array.from(event.target.files || []))} />
                <button type="button" className="button secondary" disabled={!attachmentFiles.length || uploadingAttachments} onClick={uploadAttachments}>{uploadingAttachments ? 'Uploading…' : `Add Attachment${attachmentFiles.length === 1 ? '' : 's'}`}</button>
              </div>
              <div className="muted file-help">Up to 25 MB per attachment.</div>
            </div>
          </div>
        </section>

      </div>

      <aside className="panel"><div className="panel-header">Ticket Information</div><div className="panel-body"><dl className="detail-list"><dt>Table</dt><dd>{p.table_name || '—'}</dd><dt>Ticket ID</dt><dd>{p.problem_number}</dd><dt>Date Created</dt><dd>{p.created_at ? new Date(p.created_at).toLocaleString() : '—'}</dd><dt>Container ID</dt><dd>{p.container_id ? <Link className="table-link" href={`/disposal/containers/all#container-${p.container_id}`}>{p.container_id}</Link> : 'Unassigned'}</dd><dt>Ticket expiration period</dt><dd>{(p.pt_days ?? table?.pt_days ?? 30) === 0 ? 'Immediate when Dispose Automatically is changed to Yes' : `${p.pt_days ?? table?.pt_days ?? 30} day${(p.pt_days ?? table?.pt_days ?? 30) === 1 ? '' : 's'} from the most recent change of Dispose Automatically from No to Yes`}</dd><dt>Customer notified</dt><dd>{p.customer_notified_at ? new Date(p.customer_notified_at).toLocaleString() : 'Not yet confirmed'}</dd><dt>Automatic disposal started</dt><dd>{p.automatic_disposal_started_at ? new Date(p.automatic_disposal_started_at).toLocaleString() : 'Not active'}</dd><dt>Expires</dt><dd>{p.expires_at ? new Date(p.expires_at).toLocaleString() : '—'}</dd><dt>Expiration status</dt><dd>{p.expiration_status === 'expired' ? 'Expired' : 'Active'}</dd><dt>Internal Row ID</dt><dd>{p.id}</dd><dt>Columns</dt><dd>{table?.columns.length || 0}</dd><dt>Images</dt><dd>{p.images?.length || 0}</dd><dt>Attachments</dt><dd>{p.attachments?.length || 0}</dd></dl></div></aside>
    </div>

    {deleteConfirmationOpen && <div className="delete-row-overlay" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget && !deletingProblem) setDeleteConfirmationOpen(false); }}>
      <div className="delete-row-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-row-title" aria-describedby="delete-row-description">
        <div className="delete-row-icon" aria-hidden="true">!</div>
        <h2 id="delete-row-title">Delete Ticket #{p.problem_number}?</h2>
        <div id="delete-row-description" className="delete-row-copy">
          <p>This permanently deletes the ticket and its comments, history, images, and attachments.</p>
          <p className="muted delete-row-note">This cannot be undone. The Ticket ID will not be reused.</p>
        </div>
        <div className="delete-row-actions">
          <button type="button" className="button secondary" onClick={() => setDeleteConfirmationOpen(false)} disabled={deletingProblem}>Cancel</button>
          <button type="button" className="button danger" onClick={deleteProblemSample} disabled={deletingProblem}>{deletingProblem ? 'Deleting…' : 'Delete Ticket'}</button>
        </div>
      </div>
    </div>}

    {historyReplyTarget && <div className="email-confirm-overlay" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget && !preparingHistoryReply) setHistoryReplyTarget(null); }}>
      <div className="email-confirm-dialog customer-email-preview" role="dialog" aria-modal="true" aria-labelledby="history-reply-title">
        <h2 id="history-reply-title">Reply to customer</h2>
        <p className="customer-email-company-reminder">Your reply will not be saved until you confirm that the generated customer email was sent.</p>
        <div className="field"><label>Customer message</label><textarea className="textarea" readOnly value={historyReplyTarget.details.customer_requested_information || ''} /></div>
        <div className="field"><label>Staff reply <span aria-hidden="true">*</span></label><textarea className="textarea" rows={6} maxLength={4000} autoFocus value={historyReplyText} onChange={event => setHistoryReplyText(event.target.value)} disabled={preparingHistoryReply} placeholder="Type your reply…" /><div className="muted result-meta">{historyReplyText.length}/4000 characters</div></div>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="email-confirm-actions">
          <button type="button" className="button" onClick={prepareHistoryReply} disabled={preparingHistoryReply || !historyReplyText.trim()}>{preparingHistoryReply ? 'Preparing email…' : 'Submit'}</button>
          <button type="button" className="button secondary" onClick={() => { setHistoryReplyTarget(null); setHistoryReplyText(''); setError(''); }} disabled={preparingHistoryReply}>Cancel</button>
        </div>
      </div>
    </div>}

    {historyReplyEmailDraft && <CustomerHistoryReplyEmailModal email={historyReplyEmailDraft.email} launchedAt={historyReplyEmailDraft.launchedAt} onSent={confirmHistoryReplySent} onCancel={() => { setHistoryReplyEmailDraft(null); setError(''); }} busy={savingHistoryReply} error={error} />}

    {changeReasonModal}

    {pendingEmailLaunch && <CustomerEmailModal content={pendingEmailLaunch.content} onSent={confirmEmailSent} onDidNotSend={recordCustomerEmailNotSent} onCancel={dismissEmailLaunch} busy={recordingEmailSent} error={error} />}
    {generalEmailOpen && <GeneralCustomerEmailModal recipients={customerEmails} problemNumber={p.problem_number} onSent={confirmGeneralEmailSent} onCancel={() => { setGeneralEmailOpen(false); setError(''); }} busy={recordingGeneralEmail} error={error} />}
    {testingEmailDraft && <BackToTestingEmailModal key={`${id}-${testingEmailDraft.mode}`} details={testingDetails()} onConfirm={finishTestingEmail} onCancel={() => setTestingEmailDraft(null)} busy={testingEmailBusy} error={testingEmailError} />}
    {mentionEmailDraft && <MentionEmailModal emails={mentionEmailDraft.emails} onComplete={() => saveComment(mentionEmailDraft.body, mentionEmailDraft.confirmationToken).catch(() => {})} onCancel={() => setMentionEmailDraft(null)} busy={savingMentionComment} error={error} />}
  </div>;
}
