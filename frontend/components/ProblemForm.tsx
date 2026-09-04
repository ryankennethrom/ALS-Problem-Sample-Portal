'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { automaticDisposalDisplay, CustomValues, initialValue, ProblemTable } from '@/lib/problemTables';
import DynamicField from '@/components/DynamicField';
import { buildCustomerMailto, CustomerEmailContext, findCustomerEmails, invokeCustomerEmail } from '@/lib/customerEmail';

export default function ProblemForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedTable = searchParams.get('table') || '';
  const [error, setError] = useState('');
  const [tables, setTables] = useState<ProblemTable[]>([]);
  const [containerMode, setContainerMode] = useState<'existing' | 'new'>('existing');
  const [containerId, setContainerId] = useState('');
  const [recentContainerId, setRecentContainerId] = useState('');
  const [newContainerId, setNewContainerId] = useState('');
  const [creatingContainer, setCreatingContainer] = useState(false);
  const [customValues, setCustomValues] = useState<CustomValues>({});
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [attachmentFiles, setAttachmentFiles] = useState<File[]>([]);
  const [pendingEmailLaunch, setPendingEmailLaunch] = useState<{ problemId: string; customerEmails: string[]; emailContext: CustomerEmailContext; trackingToken: string } | null>(null);
  const [emailConfirmation, setEmailConfirmation] = useState<{ problemId: string; trackingToken: string } | null>(null);
  const [launchingCustomerEmail, setLaunchingCustomerEmail] = useState(false);
  const [recordingEmailSent, setRecordingEmailSent] = useState(false);

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

  useEffect(() => {
    if (!table) return;
    const initial: CustomValues = {};
    for (const column of table.columns.filter(c => !c.is_system || c.field_key === 'status')) initial[column.field_key] = initialValue(column);
    setCustomValues(initial);
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
      return next;
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
    setError('');
    if (!table) {
      setError('No problem sample table is available.');
      return;
    }
    if (!containerId.trim()) {
      setError(containerMode === 'new' ? 'Create a new container before saving this problem sample.' : 'Enter the Container ID for this problem sample.');
      return;
    }
    try {
      const d = await api('/problem-samples/', { method: 'POST', body: JSON.stringify({ table: tableId, container_code: containerId.trim(), custom_values: customValues }), successMessage:'Problem sample created successfully.', errorMessage:'Could not create problem sample' });

      for (const file of imageFiles) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('include_in_customer_notification', 'false');
        try {
          await api(`/problem-samples/${d.id}/images/`, { method: 'POST', body: formData, errorMessage: `Could not upload image ${file.name}` });
        } catch {
          // The row already exists. Continue so a failed file upload never causes
          // the user to accidentally create the same problem sample twice.
        }
      }
      for (const file of attachmentFiles) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('include_in_customer_notification', 'false');
        try {
          await api(`/problem-samples/${d.id}/attachments/`, { method: 'POST', body: formData, errorMessage: `Could not upload attachment ${file.name}` });
        } catch {
          // See image upload note above. The API toast identifies the failed file.
        }
      }

      const savedValues: CustomValues = d.custom_values || customValues;
      const customerEmails = findCustomerEmails(table, savedValues);
      if (customerEmails.length) {
        const credentials = await api(`/problem-samples/${d.id}/customer-notification-credentials/`, {
          method: 'POST',
          errorMessage: 'Could not prepare problem sample tracking link',
        });
        const emailContext = {
          table,
          values: savedValues,
          problemNumber: d.problem_number,
          tableName: table.name,
          additionalTo: ['NAEDM.DE@ALSGlobal.com'],
          trackingUrl: credentials.tracking_url,
        };
        setPendingEmailLaunch({
          problemId: String(d.id),
          customerEmails,
          emailContext,
          trackingToken: credentials.tracking_token,
        });
        return;
      }
      router.push(`/problems/${d.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed');
    }
  }


  function cancelEmailLaunch() {
    if (!pendingEmailLaunch || launchingCustomerEmail) return;
    router.push(`/problems/${pendingEmailLaunch.problemId}`);
  }

  async function launchCustomerEmail() {
    if (!pendingEmailLaunch || launchingCustomerEmail) return;
    setError('');
    setLaunchingCustomerEmail(true);
    try {
      const mailto = await buildCustomerMailto(
        pendingEmailLaunch.customerEmails,
        pendingEmailLaunch.emailContext,
      );
      invokeCustomerEmail(mailto);
      setEmailConfirmation({
        problemId: pendingEmailLaunch.problemId,
        trackingToken: pendingEmailLaunch.trackingToken,
      });
      setPendingEmailLaunch(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not prepare customer notification');
    } finally {
      setLaunchingCustomerEmail(false);
    }
  }

  function finishEmailConfirmation() {
    if (!emailConfirmation) return;
    router.push(`/problems/${emailConfirmation.problemId}`);
  }

  async function confirmEmailSent() {
    if (!emailConfirmation || recordingEmailSent) return;
    setError('');
    setRecordingEmailSent(true);
    try {
      await api(`/problem-samples/${emailConfirmation.problemId}/customer-notification-sent/`, {
        method: 'POST',
        body: JSON.stringify({
          delivery_method: 'mailto',
          tracking_token: emailConfirmation.trackingToken,
        }),
        successMessage: 'Customer notification recorded. The automatic-disposal countdown has started when applicable.',
        errorMessage: 'Could not record customer notification',
      });
      router.push(`/problems/${emailConfirmation.problemId}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not record customer notification');
    } finally {
      setRecordingEmailSent(false);
    }
  }

  return <>
  <form className="stack" onSubmit={submit}>
    <section className="panel panel-blue container-create-panel">
      <div className="panel-header"><strong>Container</strong><span className="muted file-header-note">Required</span></div>
      <div className="panel-body stack">
        <div className="container-mode-row" role="radiogroup" aria-label="Choose container">
          <label className="check-label"><input type="radio" name="container-mode" checked={containerMode === 'existing'} onChange={() => { setContainerMode('existing'); setNewContainerId(''); }} /> Use an existing container</label>
          <label className="check-label"><input type="radio" name="container-mode" checked={containerMode === 'new'} onChange={() => { setContainerMode('new'); setContainerId(''); setNewContainerId(''); }} /> Create a new container</label>
        </div>
        {containerMode === 'existing' ? <div className="field" style={{maxWidth:420}}>
          <label htmlFor="container-id">Container ID</label>
          <input id="container-id" className="input" value={containerId} onChange={e => setContainerId(e.target.value)} placeholder={recentContainerId || 'e.g. PC-000123'} required />
          {recentContainerId && <div className="recent-container-suggestion">
            <span className="muted result-meta">Most recently created available container:</span>
            <button type="button" className="button secondary recent-container-button" onClick={() => setContainerId(recentContainerId)}>Use {recentContainerId}</button>
          </div>}
          <div className="muted result-meta">Enter the ID printed or displayed for the container. The system verifies it when the problem sample is saved.</div>
        </div> : <div className="new-container-box">
          {!newContainerId ? <>
            <div><strong>Create a new container</strong></div>
            <div className="muted result-meta">The system will assign the next Container ID. Create it first so you can label the physical container before saving the problem sample.</div>
            <div><button type="button" className="button secondary" onClick={createContainer} disabled={creatingContainer}>{creatingContainer ? 'Creating…' : 'Create New Container'}</button></div>
          </> : <>
            <div className="new-container-success-label">New Container ID</div>
            <div className="new-container-id">{newContainerId}</div>
            <div className="muted result-meta">Use this ID on the physical container. This problem sample will be assigned to it when saved.</div>
            <div><button type="button" className="button secondary" onClick={() => { setContainerId(''); setNewContainerId(''); }}>Create a different container</button></div>
          </>}
        </div>}
        {table && <div className="pt-create-note"><strong>Problem sample expiration period:</strong> {table.pt_days === 0 ? 'Immediate when Automatically Disposed is activated' : `${table.pt_days} day${table.pt_days === 1 ? '' : 's'} from the most recent switch to Automatically Disposed` }.</div>}
      </div>
    </section>

    {table ? <>
      <div className="grid">
        <div className="field readonly-field"><label>Problem ID</label><input className="input readonly-input" value="Assigned automatically when saved" disabled readOnly aria-disabled="true" /></div>
        {table.columns.filter(c => !c.is_system || ['status', 'system-days-until-automatic-disposal', 'system-tracking-link', 'system-tracking-link-expiry'].includes(c.field_key)).map(column => column.field_key === 'system-days-until-automatic-disposal'
          ? <div className="field readonly-field" key={column.id}><label>{column.name}</label><input className="input readonly-input" value={automaticDisposalDisplay({custom_values: customValues})} disabled readOnly aria-disabled="true" /></div>
          : column.field_key === 'system-tracking-link'
            ? <div className="field readonly-field" key={column.id}><label>{column.name}</label><input className="input readonly-input" value="Created when the first customer email is confirmed sent" disabled readOnly aria-disabled="true" /></div>
            : column.field_key === 'system-tracking-link-expiry'
              ? <div className="field readonly-field" key={column.id}><label>{column.name}</label><input className="input readonly-input" value="Does not expire yet" disabled readOnly aria-disabled="true" /></div>
              : <DynamicField key={column.id} column={column} value={customValues[column.field_key]} allValues={customValues} onChange={value => updateCustomValue(column.id, column.field_key, value)}/>) }
      </div>
      {table.columns.filter(c => !c.is_system || ['status', 'system-days-until-automatic-disposal', 'system-tracking-link', 'system-tracking-link-expiry'].includes(c.field_key)).length === 0 && <div className="muted">This table currently has only its built-in columns. You can create a row now or add more columns.</div>}
    </> : null}

    <section className="panel file-create-panel">
      <div className="panel-header"><strong>Images & Attachments</strong><span className="muted file-header-note">Optional</span></div>
      <div className="panel-body"><div className="muted file-notification-note">Images and attachments are stored with the problem sample. Customer notification emails are opened normally in your email application without attaching these files.</div><div className="file-upload-grid">
        <div className="field">
          <label>Images</label>
          <input className="file-control" type="file" accept="image/jpeg,image/png,image/gif,image/webp" multiple onChange={event => setImageFiles(Array.from(event.target.files || []))} />
          <div className="muted file-help">JPEG, PNG, GIF, or WebP. Up to 25 MB per image.{imageFiles.length ? ` ${imageFiles.length} selected.` : ''}</div>
        </div>
        <div className="field">
          <label>Attachments</label>
          <input className="file-control" type="file" multiple onChange={event => setAttachmentFiles(Array.from(event.target.files || []))} />
          <div className="muted file-help">Documents, spreadsheets, PDFs, archives, and other supporting files. Up to 25 MB each.{attachmentFiles.length ? ` ${attachmentFiles.length} selected.` : ''}</div>
        </div>
      </div></div>
    </section>

    {error && <div className="error">{error}</div>}
    {table ? <div><button className="button">Create Problem Sample</button></div> : null}
  </form>

  {pendingEmailLaunch && <div className="email-confirm-overlay" role="presentation">
    <div className="email-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="email-launch-title" aria-describedby="email-launch-description">
      <div className="email-confirm-icon" aria-hidden="true">✉</div>
      <h2 id="email-launch-title">Prepare the customer notification</h2>
      <div id="email-launch-description" className="email-confirm-copy">
        <p>The <strong>OK</strong> button below will open your email application and construct the appropriate customer notification email. Review the recipients and message carefully, send it when ready, then come back here for further instructions.</p>
        <p className="muted email-confirm-note">The system will not mark the customer as notified until you return and confirm that the email was sent.</p>
        {error && <div className="error" style={{marginTop:12}}>{error}</div>}
      </div>
      <div className="email-confirm-actions">
        <button type="button" className="button" onClick={launchCustomerEmail} disabled={launchingCustomerEmail}>{launchingCustomerEmail ? 'Preparing…' : 'OK'}</button>
        <button type="button" className="button secondary" onClick={cancelEmailLaunch} disabled={launchingCustomerEmail}>Cancel</button>
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
        <button type="button" className="button secondary" onClick={finishEmailConfirmation} disabled={recordingEmailSent}>I didn&apos;t</button>
      </div>
    </div>
  </div>}
  </>;
}
