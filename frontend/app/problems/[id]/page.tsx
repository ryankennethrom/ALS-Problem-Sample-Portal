'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { automaticDisposalDisplay, CustomValues, displayCustomValue, ProblemTable } from '@/lib/problemTables';
import DynamicField from '@/components/DynamicField';
import { buildCustomerMailto, CustomerEmailContext, findCustomerEmails, invokeCustomerEmail } from '@/lib/customerEmail';
import { changeReasonHeaders } from '@/lib/changeReason';
import { useChangeReasonModal } from '@/components/ChangeReasonModal';

type Comment = { id: number; body: string; author_email: string; legacy_author: string; created_at: string };
type ProblemImage = { id:number; image:string; original_name:string; size_bytes:number; include_in_customer_notification:boolean; uploaded_by_email:string; uploaded_at:string };
type ProblemAttachment = { id:number; file:string; original_name:string; content_type:string; size_bytes:number; include_in_customer_notification:boolean; uploaded_by_email:string; uploaded_at:string };
type HistoryEntry = {
  id: number;
  action: 'created' | 'updated' | 'comment' | 'customer_notification' | 'acknowledged';
  action_label: string;
  summary: string;
  details: { changes?: { field:string; before:unknown; after:unknown }[]; comment?: string; reason?: string; customer_signature?: string; customer_requested_information?: string };
  actor_email: string;
  actor_name: string;
  created_at: string;
};
type Problem = { id: string; problem_number:number; created_at:string; table:string; table_name:string; container_id:string; customer_notified_at:string|null; automatic_disposal_started_at:string|null; expires_at:string|null; expiration_status:'active'|'expired'; days_until_expiration:number|null; days_until_automatic_disposal:number|null; pt_days:number; tracking_url:string; tracking_link_expiry:string|null; acknowledged_at:string|null; comments: Comment[]; history: HistoryEntry[]; images: ProblemImage[]; attachments: ProblemAttachment[]; custom_values: CustomValues };

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
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { requestChangeReason, changeReasonModal } = useChangeReasonModal();
  const [p, setP] = useState<Problem | null>(null);
  const [table, setTable] = useState<ProblemTable | null>(null);
  const [customValues, setCustomValues] = useState<CustomValues>({});
  const [containerCode, setContainerCode] = useState('');
  const [comment, setComment] = useState('');
  const [error, setError] = useState('');
  const [saved, setSaved] = useState('');
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [attachmentFiles, setAttachmentFiles] = useState<File[]>([]);
  const [imageInputKey, setImageInputKey] = useState(0);
  const [attachmentInputKey, setAttachmentInputKey] = useState(0);
  const [uploadingImages, setUploadingImages] = useState(false);
  const [uploadingAttachments, setUploadingAttachments] = useState(false);
  const [pendingEmailLaunch, setPendingEmailLaunch] = useState<{ customerEmails: string[]; emailContext: CustomerEmailContext; trackingToken: string } | null>(null);
  const [emailConfirmation, setEmailConfirmation] = useState<{ trackingToken: string } | null>(null);
  const [recordingEmailSent, setRecordingEmailSent] = useState(false);
  const [preparingCustomerEmail, setPreparingCustomerEmail] = useState(false);
  const [deleteConfirmationOpen, setDeleteConfirmationOpen] = useState(false);
  const [deletingProblem, setDeletingProblem] = useState(false);

  async function load() {
    try {
      const problem: Problem = await api(`/problem-samples/${id}/`);
      setP(problem); setCustomValues(problem.custom_values || {}); setContainerCode(problem.container_id || '');
      if (problem.table) setTable(await api(`/problem-tables/${problem.table}/`));
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed'); }
  }
  useEffect(() => { load(); }, [id]);
  function updateCustomValue(columnId: string, fieldKey: string, value: unknown) {
    if (!table) return;
    setCustomValues(current => {
      const next = { ...current, [fieldKey]: value };
      for (const candidate of table.columns) {
        if (candidate.column_type === 'client_email' && (candidate.client_email_dependencies || []).includes(columnId)) {
          next[candidate.field_key] = '';
        }
      }
      return next;
    });
  }

  async function add() { if (!comment.trim()) return; try { await api(`/problem-samples/${id}/comments/`, { method: 'POST', body: JSON.stringify({ body: comment }), successMessage:'Comment added successfully.', errorMessage:'Could not add comment' }); setComment(''); await load(); } catch (e) { setError(e instanceof Error ? e.message : 'Failed to add comment'); } }
  async function saveCustom() {
    setSaved(''); setError('');
    const requestedContainer = containerCode.trim();
    if (!requestedContainer) {
      setError('Enter a Container ID for this problem sample.');
      return;
    }
    const reason = await requestChangeReason('Why are you changing this problem sample row?');
    if (reason === null) return;
    try {
      const updated = await api(`/problem-samples/${id}/`, {
        method:'PATCH',
        headers: changeReasonHeaders(reason),
        body:JSON.stringify({custom_values:customValues, container_code:requestedContainer}),
        successMessage:'Problem sample saved successfully.',
        errorMessage:'Could not save problem sample',
      });
      setP(updated);
      setCustomValues(updated.custom_values || {});
      setContainerCode(updated.container_id || requestedContainer);
      setSaved('Problem sample saved.');
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
        successMessage:`Problem #${p.problem_number} deleted successfully.`,
        errorMessage:'Could not delete problem sample',
      });
      setDeleteConfirmationOpen(false);
      router.push(destinationTable ? `/?table=${encodeURIComponent(destinationTable)}` : '/');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete problem sample');
      setDeletingProblem(false);
    }
  }

  if (error && !p) return <div className="card error">{error}</div>;
  if (!p) return <div>Loading…</div>;

  const customerEmails = findCustomerEmails(table, customValues);
  const rowTitle = `Problem #${p.problem_number}`;

  async function emailCustomer() {
    if (!customerEmails.length || preparingCustomerEmail) return;
    setError('');
    setPreparingCustomerEmail(true);
    try {
      const credentials = await api(`/problem-samples/${p.id}/customer-notification-credentials/`, {
        method: 'POST',
        errorMessage: 'Could not prepare problem sample tracking link',
      });
      const emailContext: CustomerEmailContext = {
        table,
        values: customValues,
        problemNumber: p.problem_number,
        tableName: p.table_name,
        trackingUrl: credentials.tracking_url,
      };
      setPendingEmailLaunch({
        customerEmails: [...customerEmails],
        emailContext,
        trackingToken: credentials.tracking_token,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not prepare customer notification');
    } finally {
      setPreparingCustomerEmail(false);
    }
  }

  async function launchCustomerEmail() {
    if (!pendingEmailLaunch || preparingCustomerEmail) return;
    setError('');
    setPreparingCustomerEmail(true);
    try {
      const mailto = await buildCustomerMailto(pendingEmailLaunch.customerEmails, pendingEmailLaunch.emailContext);
      invokeCustomerEmail(mailto);
      setEmailConfirmation({
        trackingToken: pendingEmailLaunch.trackingToken,
      });
      setPendingEmailLaunch(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not prepare customer notification');
    } finally {
      setPreparingCustomerEmail(false);
    }
  }

  function dismissEmailLaunch() {
    if (preparingCustomerEmail) return;
    setPendingEmailLaunch(null);
    setError('');
  }

  function dismissEmailConfirmation() {
    if (recordingEmailSent) return;
    setEmailConfirmation(null);
  }

  async function confirmEmailSent() {
    if (!emailConfirmation || recordingEmailSent) return;
    setError('');
    setRecordingEmailSent(true);
    try {
      await api(`/problem-samples/${id}/customer-notification-sent/`, {
        method:'POST',
        body:JSON.stringify({
          delivery_method: 'mailto',
          tracking_token: emailConfirmation.trackingToken,
        }),
        successMessage:'Customer notification recorded. The automatic-disposal countdown has started when applicable.',
        errorMessage:'Could not record customer notification',
      });
      setEmailConfirmation(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not record customer notification');
    } finally {
      setRecordingEmailSent(false);
    }
  }

  return <div>
    <div className="row" style={{marginBottom:14}}>
      <div style={{marginRight:'auto'}}><div className="eyebrow">{p.table_name || 'Problem Samples'}</div><h1 className="page-heading" style={{marginBottom:0}}>{rowTitle}</h1></div>
      {table && <Link className="button secondary" href={`/tables/${table.id}`}>Manage Columns</Link>}
      {customerEmails.length > 0 && <button type="button" className="button" onClick={emailCustomer} disabled={preparingCustomerEmail}>{preparingCustomerEmail ? 'Preparing…' : 'Email Customer'}</button>}
      <button type="button" className="button danger" onClick={() => setDeleteConfirmationOpen(true)}>Delete Row</button>
    </div>
    {error && <div className="card error" style={{marginBottom:14}}>{error}</div>}
    {saved && <div className="card success" style={{marginBottom:14}}>{saved}</div>}

    <section className={`sample-expiration-banner sample-expiration-${p.expiration_status}`} style={{marginBottom:14}}>
      <div>
        <div className="sample-expiration-title">
          <span>Container {p.container_id || 'Unassigned'}</span>
          {p.expiration_status === 'expired' ? <span className="badge expiration-expired">Expired</span> : <span className="badge expiration-active">{p.days_until_expiration ?? '—'} day{p.days_until_expiration === 1 ? '' : 's'} remaining</span>}
        </div>
        <div className="muted result-meta">Expiration period: {(p.pt_days ?? table?.pt_days ?? 30) === 0 ? 'Immediate' : `${p.pt_days ?? table?.pt_days ?? 30} day${(p.pt_days ?? table?.pt_days ?? 30) === 1 ? '' : 's'}`}. {p.customer_notified_at ? `Customer notified ${new Date(p.customer_notified_at).toLocaleString()}.` : 'Expiration begins when the customer notification is first confirmed as sent.'}</div>
      </div>
      <div className="sample-expiration-side">{p.expires_at ? <>Expires<br/><strong>{new Date(p.expires_at).toLocaleString()}</strong></> : 'No expiration date yet'}</div>
    </section>

    <section className="panel history-panel" style={{marginBottom:14}}>
      <div className="panel-header"><strong>History</strong><span className="history-count">{p.history?.length || 0} activities</span></div>
      <div className="panel-body history-list">
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
              {entry.details?.customer_requested_information && <div className="history-customer-information"><strong>Information provided by customer:</strong><div>{entry.details.customer_requested_information}</div></div>}
              {entry.action === 'comment' && entry.details?.comment && <div className="history-comment">{entry.details.comment}</div>}
              {(entry.action === 'updated' || entry.action === 'customer_notification' || entry.action === 'acknowledged') && changes.length > 0 && <div className="history-changes">
                {changes.map((change, index) => <div className="history-change" key={`${entry.id}-${index}`}>
                  <span className="history-field">{change.field}</span>
                  <span className="history-before">{displayHistoryValue(change.before)}</span>
                  <span className="history-arrow">→</span>
                  <span className="history-after">{displayHistoryValue(change.after)}</span>
                </div>)}
              </div>}
              {entry.action === 'updated' && changes.length === 0 && <div className="muted history-no-change">No field values changed.</div>}
            </div>
          </div>;
        })}
      </div>
    </section>

    <div className="two-col">
      <div className="stack">
        <section className="panel panel-blue"><div className="panel-header">Problem Sample</div><div className="panel-body stack">
          {table ? <><div className="grid"><div className="field readonly-field"><label>Problem ID</label><input className="input readonly-input" value={p.problem_number} disabled readOnly aria-disabled="true" /></div><div className="field readonly-field"><label>Date Created</label><input className="input readonly-input" value={p.created_at ? new Date(p.created_at).toLocaleString() : '—'} disabled readOnly aria-disabled="true" /></div><div className="field"><label htmlFor="edit-container-id">Container ID</label><input id="edit-container-id" className="input" value={containerCode} onChange={event=>setContainerCode(event.target.value)} placeholder="e.g. PC-000123" /><div className="muted result-meta">Enter another existing Container ID to move this problem sample when you save.</div></div>{table.columns.filter(c => !c.is_system || ['status', 'system-days-until-automatic-disposal', 'system-tracking-link', 'system-tracking-link-expiry'].includes(c.field_key)).map(column => column.field_key === 'system-days-until-automatic-disposal'
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
            <div className="muted file-notification-note">Images and attachments are stored with the problem sample. Customer notification emails are opened normally in your email application without attaching these files.</div>
            <div className="file-subsection">
              <div className="file-subsection-heading"><strong>Images</strong><span className="muted">{p.images?.length || 0}</span></div>
              {(p.images || []).length > 0 && <div className="image-gallery">
                {(p.images || []).map(image => <article className="image-card" key={image.id}>
                  <a className="image-preview-link" href={image.image} target="_blank" rel="noreferrer"><img className="image-preview" src={image.image} alt={image.original_name || 'Problem sample image'} /></a>
                  <div className="image-card-copy"><div className="file-name">{image.original_name || 'Image'}</div><div className="file-meta">{formatBytes(image.size_bytes)} · {new Date(image.uploaded_at).toLocaleString()}</div></div>
                  <button type="button" className="file-delete" onClick={() => removeImage(image)}>Delete</button>
                </article>)}
              </div>}
              {(p.images || []).length === 0 && <div className="muted file-empty">No images added.</div>}
              <div className="file-upload-row">
                <input key={imageInputKey} className="file-control" type="file" accept="image/jpeg,image/png,image/gif,image/webp" multiple onChange={event => setImageFiles(Array.from(event.target.files || []))} />
                <button type="button" className="button secondary" disabled={!imageFiles.length || uploadingImages} onClick={uploadImages}>{uploadingImages ? 'Uploading…' : `Add Image${imageFiles.length === 1 ? '' : 's'}`}</button>
              </div>
              <div className="muted file-help">JPEG, PNG, GIF, or WebP · maximum 25 MB each</div>
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

        <section className="panel"><div className="panel-header">Comments / Follow Up</div><div className="panel-body">
          {p.comments.length === 0 && <div className="muted" style={{marginBottom:12}}>No follow-up comments yet.</div>}
          {p.comments.map(c => <div className="comment-item" key={c.id}><div>{c.body}</div><div className="muted" style={{fontSize:12, marginTop:4}}>{c.author_email || c.legacy_author || 'Unknown'} · {new Date(c.created_at).toLocaleString()}</div></div>)}
          <div className="field" style={{marginTop:14}}><label>Add Follow Up</label><textarea className="textarea" placeholder="Add follow-up…" value={comment} onChange={e => setComment(e.target.value)}/></div><div style={{marginTop:10}}><button className="button" onClick={add}>Add Comment</button></div>
        </div></section>
      </div>

      <aside className="panel"><div className="panel-header">Row Information</div><div className="panel-body"><dl className="detail-list"><dt>Table</dt><dd>{p.table_name || '—'}</dd><dt>Problem ID</dt><dd>{p.problem_number}</dd><dt>Date Created</dt><dd>{p.created_at ? new Date(p.created_at).toLocaleString() : '—'}</dd><dt>Container ID</dt><dd>{p.container_id ? <Link className="table-link" href={`/disposal/containers/all#container-${p.container_id}`}>{p.container_id}</Link> : 'Unassigned'}</dd><dt>Problem sample expiration period</dt><dd>{(p.pt_days ?? table?.pt_days ?? 30) === 0 ? 'Immediate when Automatically Disposed is activated' : `${p.pt_days ?? table?.pt_days ?? 30} day${(p.pt_days ?? table?.pt_days ?? 30) === 1 ? '' : 's'} from the most recent switch to Automatically Disposed`}</dd><dt>Customer notified</dt><dd>{p.customer_notified_at ? new Date(p.customer_notified_at).toLocaleString() : 'Not yet confirmed'}</dd><dt>Automatic disposal started</dt><dd>{p.automatic_disposal_started_at ? new Date(p.automatic_disposal_started_at).toLocaleString() : 'Not active'}</dd><dt>Expires</dt><dd>{p.expires_at ? new Date(p.expires_at).toLocaleString() : '—'}</dd><dt>Expiration status</dt><dd>{p.expiration_status === 'expired' ? 'Expired' : 'Active'}</dd><dt>Internal Row ID</dt><dd>{p.id}</dd><dt>Columns</dt><dd>{table?.columns.length || 0}</dd><dt>Images</dt><dd>{p.images?.length || 0}</dd><dt>Attachments</dt><dd>{p.attachments?.length || 0}</dd></dl></div></aside>
    </div>

    {deleteConfirmationOpen && <div className="delete-row-overlay" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget && !deletingProblem) setDeleteConfirmationOpen(false); }}>
      <div className="delete-row-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-row-title" aria-describedby="delete-row-description">
        <div className="delete-row-icon" aria-hidden="true">!</div>
        <h2 id="delete-row-title">Delete Problem #{p.problem_number}?</h2>
        <div id="delete-row-description" className="delete-row-copy">
          <p>This permanently deletes the problem sample row and its comments, history, images, and attachments.</p>
          <p className="muted delete-row-note">This cannot be undone. The Problem ID will not be reused.</p>
        </div>
        <div className="delete-row-actions">
          <button type="button" className="button secondary" onClick={() => setDeleteConfirmationOpen(false)} disabled={deletingProblem}>Cancel</button>
          <button type="button" className="button danger" onClick={deleteProblemSample} disabled={deletingProblem}>{deletingProblem ? 'Deleting…' : 'Delete Problem Sample'}</button>
        </div>
      </div>
    </div>}

    {changeReasonModal}

    {pendingEmailLaunch && <div className="email-confirm-overlay" role="presentation">
      <div className="email-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="email-launch-title" aria-describedby="email-launch-description">
        <div className="email-confirm-icon" aria-hidden="true">✉</div>
        <h2 id="email-launch-title">Prepare the customer notification</h2>
        <div id="email-launch-description" className="email-confirm-copy">
          <p>The <strong>OK</strong> button below will open your email application and construct the appropriate customer notification email. Review the recipients and message carefully, send it when ready, then come back here for further instructions.</p>
          <p className="muted email-confirm-note">The system will not record the customer notification until you return and confirm that the email was sent.</p>
          {error && <div className="error" style={{marginTop:12}}>{error}</div>}
        </div>
        <div className="email-confirm-actions">
          <button type="button" className="button" onClick={launchCustomerEmail} disabled={preparingCustomerEmail}>{preparingCustomerEmail ? 'Preparing…' : 'OK'}</button>
          <button type="button" className="button secondary" onClick={dismissEmailLaunch} disabled={preparingCustomerEmail}>Cancel</button>
        </div>
      </div>
    </div>}

    {emailConfirmation && <div className="email-confirm-overlay" role="presentation">
      <div className="email-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="email-confirm-title" aria-describedby="email-confirm-description">
        <div className="email-confirm-icon" aria-hidden="true">✉</div>
        <h2 id="email-confirm-title">Did you send the email?</h2>
        <div id="email-confirm-description" className="email-confirm-copy">
          <p>Review and send the prepared customer notification in your email application. When you are finished, return here and confirm what happened.</p>
          <p className="muted email-confirm-note">Choose <strong>I sent the email</strong> only after the message has actually been sent.</p>
        </div>
        <div className="email-confirm-actions">
          <button type="button" className="button" onClick={confirmEmailSent} disabled={recordingEmailSent}>{recordingEmailSent ? 'Recording…' : 'I sent the email'}</button>
          <button type="button" className="button secondary" onClick={dismissEmailConfirmation} disabled={recordingEmailSent}>I didn&apos;t</button>
        </div>
      </div>
    </div>}
  </div>;
}
