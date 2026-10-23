'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { applyIntercolumnRules, CustomValues, initialValue, ProblemTable, resolveProblemTypeMask, MaskFieldState } from '@/lib/problemTables';
import DynamicField from '@/components/DynamicField';
import CustomerEmailModal from '@/components/CustomerEmailModal';
import CameraCapture from '@/components/CameraCapture';
import CreateTicketContainerFitModal from '@/components/CreateTicketContainerFitModal';
import { CustomerEmailContent, CustomerEmailContext, findCustomerEmails, prepareCustomerEmail } from '@/lib/customerEmail';

type PendingTicketCreation = {
  preparedId: string;
  problemNumber: number;
  trackingUrl: string;
  emailContent: CustomerEmailContent | null;
};

export default function ProblemForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedTable = searchParams.get('table') || '';
  const [error, setError] = useState('');
  const [tables, setTables] = useState<ProblemTable[]>([]);
  const [containerMode, setContainerMode] = useState<'existing' | 'new'>('existing');
  const [containerId, setContainerId] = useState('');
  const [confirmedExistingContainerId, setConfirmedExistingContainerId] = useState('');
  const [showFitConfirmation, setShowFitConfirmation] = useState(false);
  const [recentContainerId, setRecentContainerId] = useState('');
  const [newContainerId, setNewContainerId] = useState('');
  const [creatingContainer, setCreatingContainer] = useState(false);
  const [customValues, setCustomValues] = useState<CustomValues>({});
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [attachmentFiles, setAttachmentFiles] = useState<File[]>([]);
  const [saving, setSaving] = useState(false);
  const [pendingCreation, setPendingCreation] = useState<PendingTicketCreation | null>(null);
  // A server timestamp is recorded on the first Create Ticket click, including
  // time spent on the physical container check and customer email preview.
  // Only a successfully finalized ticket is included in the admin totals.
  const timingStartRef = useRef<Promise<string> | null>(null);
  function ensureCreationTimer(): Promise<string> {
    if (!timingStartRef.current) {
      timingStartRef.current = api('/ticket-creation-timing/start/', {
        method: 'POST', body: JSON.stringify({}),
      }).then(result => String(result.id)).catch(error => {
        timingStartRef.current = null;
        throw error;
      });
    }
    return timingStartRef.current;
  }


  useEffect(() => {
    api('/problem-tables/').then((data) => {
      const rows: ProblemTable[] = Array.isArray(data) ? data : (data.results || []);
      setTables(rows);
    }).catch(e => setError(e instanceof Error ? e.message : 'Failed to load tables'));

    api('/problem-containers/').then((data) => {
      const rows = Array.isArray(data) ? data : (data.results || []);
      const mostRecentActive = rows.find((container: { container_id?: string; disposed_at?: string | null }) => !container.disposed_at);
      setRecentContainerId(String(mostRecentActive?.container_id || ''));
    }).catch(() => {
      // The suggestion is a convenience only. Container validation still happens on save.
    });
  }, []);

  const table = useMemo(() => {
    const requested = requestedTable ? tables.find(t => t.id === requestedTable) : undefined;
    return requested || tables.find(t => t.is_default) || tables[0];
  }, [tables, requestedTable]);
  const tableId = table?.id || '';
  const mask: Record<string, MaskFieldState> = useMemo(() => table ? resolveProblemTypeMask(table, customValues) : {}, [table, customValues]);
  const imageMode = mask.images || 'shown';
  const attachmentMode = mask.attachments || 'shown';

  useEffect(() => {
    if (!table) return;
    const initial: CustomValues = {};
    for (const column of table.columns.filter(c => !c.is_system || ['current-workflow', 'dispose-automatically'].includes(c.field_key))) initial[column.field_key] = initialValue(column);
    setCustomValues(applyIntercolumnRules(table, initial));
  }, [tableId, table?.columns.length]);

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

  async function createContainer() {
    if (creatingContainer) return;
    setError('');
    setCreatingContainer(true);
    try {
      const created = await api('/problem-containers/', {
        method: 'POST',
        body: JSON.stringify({}),
        errorMessage: 'Could not create container',
      });
      const assigned = String(created.container_id || '');
      setContainerId(assigned);
      setNewContainerId(assigned);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not create container');
    } finally {
      setCreatingContainer(false);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (saving || pendingCreation) return;
    // Keyboard Enter submits also start at the initial Create Ticket action.
    void ensureCreationTimer().catch(() => {});
    setError('');
    if (!table) {
      setError('No ticket table is available.');
      return;
    }
    if (!containerId.trim()) {
      setError(containerMode === 'new'
        ? 'Create a new container before saving this ticket.'
        : 'Enter an existing Container ID or create a new container before saving.');
      return;
    }

    if (imageMode === 'required' && imageFiles.length === 0) {
      setError('At least one image is required by the selected form mask.'); return;
    }
    if (attachmentMode === 'required' && attachmentFiles.length === 0) {
      setError('At least one attachment is required by the selected form mask.'); return;
    }
    // An existing container must be physically checked before the ticket can be
    // prepared. Checking one Container ID never authorizes another Container ID.
    if (containerMode === 'existing' && confirmedExistingContainerId !== containerId.trim()) {
      setShowFitConfirmation(true);
      return;
    }
    await prepareTicket(containerId.trim());
  }

  async function prepareTicket(assignedContainerId: string) {
    if (saving || pendingCreation) return;
    if (!table) { setError('No ticket table is available.'); return; }
    setSaving(true);
    let preparedId = '';
    try {
      await ensureCreationTimer();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start ticket creation timer');
      setSaving(false);
      return;
    }
    try {
      const prepared = await api('/problem-samples/prepare-new/', {
        method: 'POST',
        body: JSON.stringify({ table: tableId, container_code: assignedContainerId, custom_values: customValues, image_count: imageMode === 'hidden' ? 0 : imageFiles.length, attachment_count: attachmentMode === 'hidden' ? 0 : attachmentFiles.length }),
        errorMessage: 'Could not prepare ticket',
      });
      preparedId = String(prepared.id || '');

      const customerEmails = findCustomerEmails(table, customValues);
      let emailContent: CustomerEmailContent | null = null;
      if (customerEmails.length) {
        const emailContext: CustomerEmailContext = {
          table,
          values: customValues,
          problemNumber: prepared.problem_number,
          tableName: table.name,
          trackingUrl: prepared.tracking_url,
          problemTypePrompts: prepared.problem_type_prompts || [],
        };
        const draft = await prepareCustomerEmail(customerEmails, emailContext);
        emailContent = draft.content;
      }

      setPendingCreation({
        preparedId,
        problemNumber: Number(prepared.problem_number),
        trackingUrl: String(prepared.tracking_url || ''),
        emailContent,
      });
    } catch (e) {
      if (preparedId) {
        try {
          await api('/problem-samples/cancel-prepared/', {
            method: 'POST',
            body: JSON.stringify({ id: preparedId }),
          });
        } catch {
          // Prepared rows are not real tickets or tracking links. If cleanup fails,
          // a later retry remains safe because finalization is explicit and idempotent.
        }
      }
      setError(e instanceof Error ? e.message : 'Could not prepare ticket');
    } finally {
      setSaving(false);
    }
  }

  async function finalizeCreation(sent: boolean, notSentReason = '') {
    if (!pendingCreation || saving) return;
    setSaving(true);
    setError('');
    try {
      const payload = new FormData();
      payload.append('creation_timing_id', await ensureCreationTimer());
      payload.append('id', pendingCreation.preparedId);
      payload.append('sent', String(sent));
      if (!sent) payload.append('not_sent_reason', notSentReason || 'User chose not to send the tracking-link email during ticket creation.');
      if (imageMode !== 'hidden') imageFiles.forEach(file => payload.append('images', file));
      if (attachmentMode !== 'hidden') attachmentFiles.forEach(file => payload.append('attachments', file));
      const result = await api('/problem-samples/create-prepared/', {
        method: 'POST',
        body: payload,
        successMessage: sent ? 'Ticket created and tracking-link email recorded.' : 'Ticket and tracking link created without sending the email.',
        errorMessage: 'Could not create ticket',
      });
      // All selected files are validated and saved with the ticket at finalization.
      setPendingCreation(null);
      timingStartRef.current = null;
      router.push(`/problems/${result.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not create ticket');
    } finally {
      setSaving(false);
    }
  }

  async function cancelPendingCreation() {
    if (!pendingCreation || saving) return;
    setSaving(true);
    setError('');
    try {
      await api('/problem-samples/cancel-prepared/', {
        method: 'POST',
        body: JSON.stringify({ id: pendingCreation.preparedId }),
        errorMessage: 'Could not cancel ticket creation',
      });
      setPendingCreation(null);
      timingStartRef.current = null;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not cancel ticket creation');
    } finally {
      setSaving(false);
    }
  }

  return <>
  <form className="stack" onSubmit={submit}>
    {tables.length > 0 && <section className="panel panel-blue">
      <div className="panel-header"><strong>Ticket Table</strong></div>
      <div className="panel-body">
        <div className="field" style={{ maxWidth: 520 }}>
          <label htmlFor="create-ticket-table">Table <span className="required-marker" aria-hidden="true">*</span></label>
          <select id="create-ticket-table" className="input" value={tableId} disabled={saving || Boolean(pendingCreation)}
            onChange={event => {
              if (!event.target.value || event.target.value === tableId) return;
              setError('');
              setImageFiles([]);
              setAttachmentFiles([]);
              router.replace(`/problems/new?table=${encodeURIComponent(event.target.value)}`);
            }}>
            {tables.map(choice => <option key={choice.id} value={choice.id}>{choice.name}{choice.is_default ? ' (Default)' : ''}</option>)}
          </select>
          <div className="muted result-meta">Choose which table will store this ticket. Switching tables resets the ticket details and selected files.</div>
        </div>
      </div>
    </section>}
    <section className="panel panel-blue container-create-panel">
      <div className="panel-header"><strong>Container</strong><span className="muted file-header-note">Required for new tickets</span></div>
      <div className="panel-body stack">
        <div className="container-mode-row" role="radiogroup" aria-label="Choose container">
          <label className="check-label"><input type="radio" name="container-mode" checked={containerMode === 'existing'} onChange={() => { setContainerMode('existing'); setNewContainerId(''); setConfirmedExistingContainerId(''); }} /> Use an existing container</label>
          <label className="check-label"><input type="radio" name="container-mode" checked={containerMode === 'new'} onChange={() => { setContainerMode('new'); setContainerId(''); setNewContainerId(''); setConfirmedExistingContainerId(''); }} /> Create a new container</label>
        </div>
        {containerMode === 'existing' ? <div className="field" style={{maxWidth:420}}>
          <label htmlFor="container-id">Container ID <span className="required-marker" aria-hidden="true">*</span></label>
          <input id="container-id" className="input" required value={containerId} onChange={e => { setContainerId(e.target.value); setConfirmedExistingContainerId(''); }} placeholder={recentContainerId || 'e.g. PC-000123'} />
          {recentContainerId && <div className="recent-container-suggestion">
            <span className="muted result-meta">Most recently created available container:</span>
            <button type="button" className="button secondary recent-container-button" onClick={() => { setContainerId(recentContainerId); setConfirmedExistingContainerId(''); }}>Use {recentContainerId}</button>
          </div>}
          <div className="muted result-meta">Enter an active Container ID or choose Create a new container. When creating the ticket, you must confirm that its samples physically fit in an existing container. The ID is verified on save.</div>
          {confirmedExistingContainerId === containerId.trim() && containerId.trim() && <div role="status" className="muted result-meta">Physical fit confirmed for {confirmedExistingContainerId}. If you change the ID, you'll be asked again.</div>}
        </div> : <div className="new-container-box">
          {!newContainerId ? <>
            <div><strong>Create a new container</strong></div>
            <div className="muted result-meta">The system will assign the next Container ID. Create it first so you can label the physical container before saving the ticket.</div>
            <div><button type="button" className="button secondary" onClick={createContainer} disabled={creatingContainer}>{creatingContainer ? 'Creating…' : 'Create New Container'}</button></div>
          </> : <>
            <div className="new-container-success-label">New Container ID</div>
            <div className="new-container-id">{newContainerId}</div>
            <div className="muted result-meta">Use this ID on the physical container. This ticket will be assigned to it when saved.</div>
            <div><button type="button" className="button secondary" onClick={() => { setContainerId(''); setNewContainerId(''); }}>Create a different container</button></div>
          </>}
        </div>}
        {table && <div className="pt-create-note"><strong>Ticket expiration period:</strong> {table.pt_days === 0 ? 'Immediate when Dispose Automatically is changed to Yes' : `${table.pt_days} day${table.pt_days === 1 ? '' : 's'} from the most recent change of Dispose Automatically from No to Yes` }.</div>}
      </div>
    </section>

    {table ? <>
      <div className="grid">
        {table.columns.filter(c => !['system-days-until-automatic-disposal', 'system-tracking-link', 'system-tracking-link-expiry'].includes(c.field_key) && (!c.is_system || ['current-workflow', 'dispose-automatically'].includes(c.field_key)) && (c.column_type === 'problem_type' || mask[c.field_key] !== 'hidden')).map(column =>
          <DynamicField key={column.id} column={{...column, required: mask[column.field_key] === 'required' || (mask[column.field_key] !== 'shown' && column.required)}} value={customValues[column.field_key]} allValues={customValues} onChange={value => updateCustomValue(column.id, column.field_key, value)}/>) }
      </div>
      {table.columns.filter(c => !['system-days-until-automatic-disposal', 'system-tracking-link', 'system-tracking-link-expiry'].includes(c.field_key) && (!c.is_system || ['current-workflow', 'dispose-automatically'].includes(c.field_key))).length === 0 && <div className="muted">This table currently has only its built-in columns. You can create a row now or add more columns.</div>}
    </> : null}

    {(imageMode !== 'hidden' || attachmentMode !== 'hidden') && <section className="panel file-create-panel">
      <div className="panel-header"><strong>Images & Attachments</strong><span className="muted file-header-note">{imageMode === 'required' || attachmentMode === 'required' ? 'Requirements set by form mask' : 'Optional'}</span></div>
      <div className="panel-body"><div className="muted file-notification-note">The tracking-link email is prepared before the ticket is created. Selected files are uploaded only after you confirm that the email was sent or not sent.</div><div className="file-upload-grid">
        {imageMode !== 'hidden' && <div className="field">
          <label>Images{imageMode === 'required' && <span className="required-marker"> *</span>}</label>
          <div className="camera-upload-controls">
            <input className="file-control" type="file" accept="image/jpeg,image/png,image/gif,image/webp" multiple onChange={event => setImageFiles(Array.from(event.target.files || []))} />
            <CameraCapture onCapture={file => setImageFiles(current => [...current, file])} disabled={saving || Boolean(pendingCreation)} />
          </div>
          <div className="muted file-help">Upload JPEG, PNG, GIF, or WebP, or take a photo with this device. Up to 25 MB per image.{imageFiles.length ? ` ${imageFiles.length} selected.` : ''}</div>
        </div>}
        {attachmentMode !== 'hidden' && <div className="field">
          <label>Attachments{attachmentMode === 'required' && <span className="required-marker"> *</span>}</label>
          <input className="file-control" type="file" multiple onChange={event => setAttachmentFiles(Array.from(event.target.files || []))} />
          <div className="muted file-help">Documents, spreadsheets, PDFs, archives, and other supporting files. Up to 25 MB each.{attachmentFiles.length ? ` ${attachmentFiles.length} selected.` : ''}</div>
        </div>}
      </div></div>
    </section>}

    {error && <div className="error">{error}</div>}
    {table ? <div><button className="button" onClick={() => { void ensureCreationTimer().catch(() => {}); }} disabled={saving || Boolean(pendingCreation)}>{saving ? 'Preparing…' : 'Create Ticket'}</button></div> : null}
  </form>
  {showFitConfirmation && containerMode === 'existing' && <CreateTicketContainerFitModal
    containerId={containerId.trim()}
    onFits={() => {
      const confirmedId = containerId.trim();
      setConfirmedExistingContainerId(confirmedId);
      setShowFitConfirmation(false);
      void prepareTicket(confirmedId);
    }}
    onDifferent={() => {
      setShowFitConfirmation(false);
      setContainerId('');
      setConfirmedExistingContainerId('');
    }}
    onCreateNew={() => {
      setShowFitConfirmation(false);
      setContainerMode('new');
      setContainerId('');
      setNewContainerId('');
      setConfirmedExistingContainerId('');
    }}
    onDismiss={() => setShowFitConfirmation(false)}
  />}
  {pendingCreation && <CustomerEmailModal
    content={pendingCreation.emailContent}
    onSent={() => finalizeCreation(true)}
    onDidNotSend={(reason) => finalizeCreation(false, reason)}
    onCancel={cancelPendingCreation}
    busy={saving}
    error={error}
    requireNotSentReason={false}
  />}
  </>;
}
