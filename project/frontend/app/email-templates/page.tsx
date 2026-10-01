'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';

type CurrentUser = { is_admin: boolean };
type EdmontonRecipient = { email: string; updated_at?: string | null; updated_by?: string };
type Template = {
  key: string;
  name: string;
  subject_template: string;
  body_template: string;
  allowed_placeholders: string[];
  required_placeholders: string[];
  default_subject_template: string;
  default_body_template: string;
  updated_at?: string | null;
  updated_by?: string;
};

export default function EmailTemplatesPage() {
  const router = useRouter();
  const [template, setTemplate] = useState<Template | null>(null);
  const [recipient, setRecipient] = useState<EdmontonRecipient | null>(null);
  const [recipientEmail, setRecipientEmail] = useState('');
  const [savingRecipient, setSavingRecipient] = useState(false);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([api('/auth/me/'), api('/email-templates/customer-notification/'), api('/email-templates/edmonton-recipient/')])
      .then(([me, data, address]: [CurrentUser, Template, EdmontonRecipient]) => {
        if (!me.is_admin) { router.replace('/'); return; }
        setTemplate(data);
        setSubject(data.subject_template);
        setBody(data.body_template);
        setRecipient(address);
        setRecipientEmail(address.email);
      })
      .catch(e => setError(e instanceof Error ? e.message : 'Could not load email templates'))
      .finally(() => setLoading(false));
  }, [router]);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!template || saving) return;
    setError('');
    setSaving(true);
    try {
      const updated: Template = await api('/email-templates/customer-notification/', {
        method: 'PUT',
        body: JSON.stringify({ subject_template: subject, body_template: body }),
        successMessage: 'Email template saved.',
        errorMessage: 'Could not save email template',
      });
      setTemplate(updated);
      setSubject(updated.subject_template);
      setBody(updated.body_template);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save email template');
    } finally {
      setSaving(false);
    }
  }

  async function saveRecipient(e: FormEvent) {
    e.preventDefault();
    if (!recipient || savingRecipient) return;
    setError(''); setSavingRecipient(true);
    try {
      const updated: EdmontonRecipient = await api('/email-templates/edmonton-recipient/', {
        method: 'PUT', body: JSON.stringify({ email: recipientEmail.trim() }),
        successMessage: 'NA.EDM address saved.', errorMessage: 'Could not save NA.EDM address',
      });
      setRecipient(updated);
      setRecipientEmail(updated.email);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save NA.EDM address');
    } finally { setSavingRecipient(false); }
  }

  function restoreDefault() {
    if (!template) return;
    if (!window.confirm('Restore the built-in subject and body in the editor? This will not be saved until you click Save Template.')) return;
    setSubject(template.default_subject_template);
    setBody(template.default_body_template);
  }

  if (loading) return <div className="muted">Loading email templates…</div>;
  if (!template) return <div className="card error">{error || 'Email template is unavailable.'}</div>;

  return <div>
    <div className="page-heading-row">
      <div>
        <h1 className="page-heading">Email Templates</h1>
        <div className="muted">Administrators can edit email copy and the NA.EDM recipient. Changes apply to future email previews immediately.</div>
      </div>
    </div>

    {error && <div className="card error" style={{marginBottom:16}}>{error}</div>}

    <form className="panel panel-blue" onSubmit={saveRecipient} style={{marginBottom:16}}>
      <div className="panel-header"><strong>NA.EDM recipient</strong></div>
      <div className="panel-body stack">
        <p className="muted">Used for the Back to Testing notification and included as a recipient when creating a ticket and emailing the customer.</p>
        <div className="field">
          <label htmlFor="edmonton-recipient">Email address <span className="required-marker" aria-hidden="true"> *</span></label>
          <input id="edmonton-recipient" type="email" className="input" required maxLength={254} value={recipientEmail} onChange={e => setRecipientEmail(e.target.value)} />
        </div>
        {recipient?.updated_at && recipient.updated_by && <div className="muted result-meta">Last saved {new Date(recipient.updated_at).toLocaleString()} by {recipient.updated_by}.</div>}
        <div><button className="button" type="submit" disabled={savingRecipient}>{savingRecipient ? 'Saving…' : 'Save NA.EDM Address'}</button></div>
      </div>
    </form>

    <form className="panel panel-blue" onSubmit={save}>
      <div className="panel-header"><strong>{template.name}</strong></div>
      <div className="panel-body stack">
        <div className="muted result-meta">This template is used by Send Tracking Link. Email Customer opens a separate general message without a tracking link.</div>
        <div className="field">
          <label htmlFor="email-template-subject">Subject <span className="required-marker" aria-hidden="true"> *</span></label>
          <input id="email-template-subject" className="input" required maxLength={500} value={subject} onChange={e => setSubject(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="email-template-body">Body <span className="required-marker" aria-hidden="true"> *</span></label>
          <textarea id="email-template-body" className="input" required maxLength={20000} value={body} onChange={e => setBody(e.target.value)} style={{minHeight:520, resize:'vertical', fontFamily:'inherit', lineHeight:1.5}} />
        </div>

        <div className="panel" style={{margin:0}}>
          <div className="panel-header">Available Placeholders</div>
          <div className="panel-body">
            <div className="muted result-meta" style={{marginBottom:10}}>Placeholders are replaced with values from the ticket when the tracking-link email is opened. <strong>{'{{tracking_link}}'}</strong> is required for this template.</div>
            <div style={{display:'flex', flexWrap:'wrap', gap:8}}>
              {template.allowed_placeholders.map(name => <code key={name} style={{padding:'5px 8px', border:'1px solid var(--border)', borderRadius:6}}>{`{{${name}}}`}{template.required_placeholders.includes(name) ? ' *' : ''}</code>)}
            </div>
          </div>
        </div>

        {template.updated_at && <div className="muted result-meta">Last saved {new Date(template.updated_at).toLocaleString()}{template.updated_by ? ` by ${template.updated_by}` : ''}.</div>}
        <div style={{display:'flex', gap:10, flexWrap:'wrap'}}>
          <button className="button" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save Template'}</button>
          <button className="button secondary" type="button" disabled={saving} onClick={restoreDefault}>Restore Built-in Copy</button>
        </div>
      </div>
    </form>
  </div>;
}
