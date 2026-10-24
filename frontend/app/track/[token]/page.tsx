'use client';

import { useEffect, useRef, useState } from 'react';
import { useParams } from 'next/navigation';

const API = '/backend-api';
const TRACKING_API = `${API}/public/problem-sample-tracking`;

type CustomerAction = '' | 'dispose' | 'ship_back' | 'hold' | 'requested_info';
type ShippingMethod = '' | 'courier_account' | 'pickup' | 'shipping_quote';

type PublicImage = { id: number; name: string; size_bytes: number };
type PublicAttachment = { id: number; name: string; size_bytes: number; content_type?: string };
type PublicDetail = { label: string; value: string };
type PublicConversationMessage = {
  id: number;
  sender: 'customer' | 'staff';
  sender_label: string;
  message: string;
  signature?: string;
  created_at: string;
  images?: PublicImage[];
  attachments?: PublicAttachment[];
};

type TrackingState = {
  state: 'pending' | 'acknowledged' | 'disposing' | 'shipping' | 'testing' | 'dumped' | 'expired';
  message: string;
  problem_number?: number;
  problem_type?: string;
  ticket_status?: string;
  acknowledged_at?: string;
  visible_until?: string;
  customer_action?: CustomerAction;
  customer_action_label?: string;
  can_choose_action?: boolean;
  automatic_disposal_active?: boolean;
  days_until_disposal?: number | null;
  details?: PublicDetail[];
  images?: PublicImage[];
  attachments?: PublicAttachment[];
  conversation?: PublicConversationMessage[];
  customer_signature?: string;
};

function formatFileSize(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(kb >= 10 ? 0 : 1)} KB`;
  const mb = kb / 1024;
  return `${mb.toFixed(mb >= 10 ? 0 : 1)} MB`;
}

function formatConversationTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
  });
}

// Browser preview for photos taken on the phone before they are sent.
function PendingChatPhoto({ file }: { file: File }) {
  const [previewUrl, setPreviewUrl] = useState('');
  useEffect(() => {
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  return previewUrl
    ? <img src={previewUrl} className="public-chat-file-chip-preview" alt="Photo ready to send" />
    : <span className="public-chat-file-chip-icon" aria-hidden="true">▧</span>;
}

const actionLabels: Record<Exclude<CustomerAction, ''>, string> = {
  dispose: 'Dispose Sample(s)',
  ship_back: 'I want these sample(s) back',
  hold: 'Hold sample',
  requested_info: 'Message us about the issue',
};

export default function ProblemSampleTrackingPage() {
  const { token } = useParams<{ token: string }>();
  const [data, setData] = useState<TrackingState | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [signature, setSignature] = useState('');
  const [requestedInfoOpen, setRequestedInfoOpen] = useState(false);
  const [returnDialogOpen, setReturnDialogOpen] = useState(false);
  const [shippingMethod, setShippingMethod] = useState<ShippingMethod>('');
  const [courierAccountNumber, setCourierAccountNumber] = useState('');
  const [requestedInformation, setRequestedInformation] = useState('');
  const [requestedImages, setRequestedImages] = useState<File[]>([]);
  const [requestedAttachments, setRequestedAttachments] = useState<File[]>([]);
  const [attachmentMenuOpen, setAttachmentMenuOpen] = useState(false);
  const autoMessageOpenHandled = useRef(false);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const cameraInputRef = useRef<HTMLInputElement | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const attachmentInputRef = useRef<HTMLInputElement | null>(null);

  const previousCustomerSignature = data?.customer_signature?.trim() || [...(data?.conversation || [])]
    .reverse()
    .find(message => message.sender === 'customer' && message.signature?.trim())
    ?.signature?.trim() || '';
  const effectiveSignature = signature.trim() || previousCustomerSignature;

  async function load() {
    setError('');
    const response = await fetch(`${TRACKING_API}/${token}/`, { cache: 'no-store' });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || 'Could not open the ticket tracking link.');
    setData(body);
  }

  useEffect(() => {
    load().catch(error => setError(error instanceof Error ? error.message : 'Could not open the ticket tracking link.'));
  }, [token]);

  useEffect(() => {
    if (!signature.trim() && previousCustomerSignature) setSignature(previousCustomerSignature);
  }, [previousCustomerSignature]);

  useEffect(() => {
    if (!requestedInfoOpen) return;
    const frame = window.requestAnimationFrame(() => {
      chatEndRef.current?.scrollIntoView({ block: 'end' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [requestedInfoOpen, data?.conversation?.length]);

  useEffect(() => {
    if (!data || autoMessageOpenHandled.current || typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    if (params.get('message') !== '1') return;
    autoMessageOpenHandled.current = true;
    if ((data.state === 'pending' || data.state === 'acknowledged') && data.can_choose_action) {
      setError('');
      setRequestedInformation('');
      setRequestedImages([]);
      setRequestedAttachments([]);
      setRequestedInfoOpen(true);
    }
  }, [data]);

  async function chooseAction(
    action: Exclude<CustomerAction, ''>,
    requestedInfo = '',
    images: File[] = [],
    attachments: File[] = [],
    returnMethod: ShippingMethod = '',
    returnCourierAccount = '',
  ) {
    const signedName = effectiveSignature;
    if (busy || !signedName) return;
    setBusy(true);
    setError('');
    try {
      let response: Response;
      if (action === 'requested_info') {
        const form = new FormData();
        form.append('action', action);
        form.append('signature', signedName);
        form.append('requested_information', requestedInfo.trim());
        images.forEach(file => form.append('images', file, file.name));
        attachments.forEach(file => form.append('attachments', file, file.name));
        response = await fetch(`${TRACKING_API}/${token}/`, { method: 'POST', body: form });
      } else {
        response = await fetch(`${TRACKING_API}/${token}/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action, signature: signedName, requested_information: requestedInfo.trim(),
            ...(action === 'ship_back' ? { shipping_method: returnMethod, courier_account_number: returnMethod === 'courier_account' ? returnCourierAccount.trim() : '' } : {}),
          }),
        });
      }
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || 'Your selection could not be recorded.');
      setData(body);
      setRequestedInformation('');
      setRequestedImages([]);
      setRequestedAttachments([]);
      if (action === 'ship_back') {
        setReturnDialogOpen(false);
        setShippingMethod('');
        setCourierAccountNumber('');
      }
      if (action === 'requested_info') {
        // Keep the chat open so the customer immediately sees the new message
        // in the conversation thread and can continue the correspondence.
        setRequestedInfoOpen(true);
      } else {
        setSignature('');
        setRequestedInfoOpen(false);
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Your selection could not be recorded.');
    } finally {
      setBusy(false);
    }
  }

  return <main className="public-ack-page">
    <section className="public-ack-card">
      <img src="/als-logo.png" alt="ALS" className="public-ack-logo" />
      <div className="eyebrow">Ticket Tracking</div>
      {error && !data ? <><h1>Unable to open link</h1><div className="card error">{error}</div></> : !data ? <h1>Loading…</h1> : <>
        <h1>{data.message}</h1>
        {data.problem_number && <div className="public-ack-problem">Ticket ID #{data.problem_number}</div>}
        {data.ticket_status && <div className="public-ticket-status">
          <span>Ticket Status</span>
          <strong>{data.ticket_status}</strong>
        </div>}

        {(data.details?.length || 0) > 0 && <section className="public-tracking-details">
          <h2>Ticket Details</h2>
          <dl className="public-tracking-detail-list">
            {data.details!.map((detail, index) => <div className="public-tracking-detail-row" key={`${detail.label}-${index}`}>
              <dt>{detail.label}</dt>
              <dd>{detail.value}</dd>
            </div>)}
          </dl>
        </section>}

        {((data.images?.length || 0) > 0 || (data.attachments?.length || 0) > 0) && <section className="public-ack-files">
          <div className="public-ack-files-heading">
            <h2>Sample images and files</h2>
            <p>Files provided with this ticket are available while this ticket tracking link is active.</p>
          </div>
          {(data.images?.length || 0) > 0 && <div className="public-ack-images">
            {data.images!.map(image => {
              const imageUrl = `${TRACKING_API}/${token}/images/${image.id}/`;
              return <a key={image.id} className="public-ack-image-card" href={imageUrl} target="_blank" rel="noreferrer">
                <img src={imageUrl} alt={image.name || `Ticket image ${image.id}`} loading="lazy" />
                <span className="public-ack-file-name">{image.name}</span>
                {formatFileSize(image.size_bytes) && <span className="public-ack-file-size">{formatFileSize(image.size_bytes)}</span>}
              </a>;
            })}
          </div>}
          {(data.attachments?.length || 0) > 0 && <div className="public-ack-attachments">
            {data.attachments!.map(file => <a
              key={file.id}
              className="public-ack-attachment"
              href={`${TRACKING_API}/${token}/attachments/${file.id}/`}
            >
              <span className="public-ack-attachment-icon" aria-hidden="true">📎</span>
              <span className="public-ack-attachment-copy">
                <span className="public-ack-file-name">{file.name}</span>
                {formatFileSize(file.size_bytes) && <span className="public-ack-file-size">{formatFileSize(file.size_bytes)}</span>}
              </span>
              <span className="public-ack-download">Download</span>
            </a>)}
          </div>}
        </section>}

        {(data.state === 'pending' || (data.state === 'acknowledged' && data.can_choose_action)) && <div className="public-ack-action-panel">
          <h2>What would you like ALS to do with the sample(s)?</h2>
          <p>Selecting an option records your requested action for this ticket.</p>
          <label className="public-tracking-signature">
            <span>Signature — type your name <strong aria-hidden="true">*</strong></span>
            <input
              type="text"
              value={signature}
              maxLength={200}
              autoComplete="name"
              onChange={event => setSignature(event.target.value)}
              placeholder="Your name"
              disabled={busy}
            />
            <small>Type your name before sending a response.</small>
          </label>
          {error && <div className="card error">{error}</div>}
          {data.customer_action && <div className="public-ack-selection">
            Current response: <strong>{data.customer_action_label || actionLabels[data.customer_action]}</strong>. You can change this response until ALS completes the requested action.
          </div>}
          <div className="public-ack-action-buttons">
            <button className="button" disabled={busy || !signature.trim()} onClick={() => chooseAction('dispose')}>Permit immediate disposal</button>
            <button className="button secondary" disabled={busy || !effectiveSignature} onClick={() => { setError(''); setRequestedInformation(''); setRequestedImages([]); setRequestedAttachments([]); setAttachmentMenuOpen(false); setRequestedInfoOpen(true); }}>Message us about the issue</button>
            <button className="button secondary" disabled={busy || !effectiveSignature} onClick={() => {
              setError(''); setShippingMethod(''); setCourierAccountNumber(''); setReturnDialogOpen(true);
            }}>I want these sample(s) back</button>
          </div>
        </div>}
        {data.state === 'acknowledged' && !data.can_choose_action && data.customer_action && <div className="public-ack-selection">
          Your response has been recorded: <strong>{data.customer_action_label || actionLabels[data.customer_action]}</strong>.
        </div>}
        {data.state === 'disposing' && <p>ALS has recorded that the sample(s) are marked for disposal.</p>}
        {data.state === 'shipping' && <p>ALS has recorded that the sample(s) are to be shipped back to the client.</p>}
        {data.state === 'testing' && <p>ALS has recorded that the sample(s) are being returned to testing.</p>}
        {data.state === 'dumped' && <p>This ticket has been disposed. No customer action is available.</p>}
        {data.state === 'expired' && <p>This ticket tracking link is no longer active.</p>}
      </>}

        {returnDialogOpen && <div className="public-requested-info-overlay" role="presentation" onMouseDown={event => {
          if (event.target === event.currentTarget && !busy) setReturnDialogOpen(false);
        }}>
          <section className="public-requested-info-dialog public-return-dialog" role="dialog" aria-modal="true" aria-labelledby="return-samples-title">
            <h2 id="return-samples-title">I want these sample(s) back</h2>
            <p>We do not charge a client handling fee. However, shipping charges still apply.</p>
            <p><strong>Please let us know which option you prefer:</strong></p>
            <div className="public-return-options" role="radiogroup" aria-label="Return method">
              <label><input type="radio" name="return-method" checked={shippingMethod === 'courier_account'} disabled={busy} onChange={() => setShippingMethod('courier_account')} />
                <span>1. Provide your courier account number, if available.</span>
              </label>
              {shippingMethod === 'courier_account' && <div className="public-return-account">
                <label htmlFor="return-courier-account">Courier account number <strong aria-hidden="true">*</strong></label>
                <input id="return-courier-account" type="text" maxLength={200} value={courierAccountNumber} onChange={event => setCourierAccountNumber(event.target.value)} autoComplete="off" disabled={busy} required placeholder="Enter your courier account number" />
              </div>}
              <label><input type="radio" name="return-method" checked={shippingMethod === 'pickup'} disabled={busy} onChange={() => setShippingMethod('pickup')} />
                <span>2. Pick up in person.</span>
              </label>
              <label><input type="radio" name="return-method" checked={shippingMethod === 'shipping_quote'} disabled={busy} onChange={() => setShippingMethod('shipping_quote')} />
                <span>3. Receive a quote for the shipping charges.</span>
              </label>
            </div>
            {error && <p className="error" role="alert">{error}</p>}
            <div className="public-requested-info-signature">Submitting as: <strong>{effectiveSignature}</strong></div>
            <div className="public-requested-info-actions">
              <button className="button secondary" type="button" disabled={busy} onClick={() => setReturnDialogOpen(false)}>Cancel</button>
              <button className="button" type="button" disabled={busy || !effectiveSignature || !shippingMethod || (shippingMethod === 'courier_account' && !courierAccountNumber.trim())} onClick={() => chooseAction('ship_back', '', [], [], shippingMethod, courierAccountNumber)}>{busy ? 'Saving…' : 'Confirm return method'}</button>
            </div>
          </section>
        </div>}

        {requestedInfoOpen && <div className="public-requested-info-overlay public-chat-overlay" role="presentation" onMouseDown={event => {
          if (event.target === event.currentTarget && !busy) setRequestedInfoOpen(false);
        }}>
          <aside className="public-chat-panel" role="dialog" aria-modal="true" aria-labelledby="customer-chat-title" aria-describedby="customer-chat-description">
            <header className="public-chat-header">
              <div className="public-chat-header-main">
                <div className="public-chat-avatar" aria-hidden="true">ALS</div>
                <div className="public-chat-header-copy">
                  <div className="public-chat-title-row">
                    <h2 id="customer-chat-title">ALS Edmonton</h2>
                    <span className="public-chat-status"><span aria-hidden="true" /> Ticket #{data?.problem_number}</span>
                  </div>
                  <p id="customer-chat-description">Message us about the issue</p>
                </div>
              </div>
              <button type="button" className="public-chat-close" aria-label="Close chat" disabled={busy} onClick={() => setRequestedInfoOpen(false)}>×</button>
            </header>

            <div className="public-chat-ticket-context" aria-label="Issue details">
              <div><span>Problem Type</span><strong>{data?.problem_type || 'Not provided'}</strong></div>
            </div>

            <div className="public-chat-thread" aria-label="Conversation history">
              {(data?.conversation?.length || 0) === 0 ? <div className="public-chat-empty">
                <div className="public-chat-empty-icon" aria-hidden="true">💬</div>
                <strong>Start a conversation</strong>
                <span>Send a message to ALS Edmonton about this ticket.</span>
              </div> : data!.conversation!.map(message => <article
                className={`public-chat-message ${message.sender === 'customer' ? 'customer' : 'staff'}`}
                key={`${message.sender}-${message.id}`}
              >
                <div className="public-chat-message-meta">
                  <strong>{message.sender_label}</strong>
                  <span>{formatConversationTime(message.created_at)}</span>
                </div>
                <div className="public-chat-bubble">
                  <div className="public-chat-message-text">{message.message}</div>
                  {(message.images?.length || 0) > 0 && <div className="public-chat-images">
                    {message.images!.map(image => {
                      const imageUrl = `${TRACKING_API}/${token}/images/${image.id}/`;
                      return <a key={image.id} href={imageUrl} target="_blank" rel="noreferrer" className="public-chat-image">
                        <img src={imageUrl} alt={image.name || `Attached image ${image.id}`} loading="lazy" />
                        <span>{image.name}</span>
                      </a>;
                    })}
                  </div>}
                  {(message.attachments?.length || 0) > 0 && <div className="public-chat-attachments">
                    {message.attachments!.map(file => <a key={file.id} href={`${TRACKING_API}/${token}/attachments/${file.id}/`} className="public-chat-attachment">
                      <span className="public-chat-file-icon" aria-hidden="true">↧</span>
                      <span>{file.name}</span>
                      {formatFileSize(file.size_bytes) && <small>{formatFileSize(file.size_bytes)}</small>}
                    </a>)}
                  </div>}
                </div>
              </article>)}
              <div ref={chatEndRef} aria-hidden="true" />
            </div>

            <div className="public-chat-composer">
              {(requestedImages.length > 0 || requestedAttachments.length > 0) && <div className="public-chat-pending-files" aria-label="Files ready to send">
                {requestedImages.map((file, index) => <div className="public-chat-file-chip" key={`image-${index}-${file.name}-${file.size}`}>
                  <PendingChatPhoto file={file} />
                  <span className="public-chat-file-chip-name">{file.name}</span>
                  <button type="button" aria-label={`Remove ${file.name}`} disabled={busy} onClick={() => setRequestedImages(files => files.filter((_, itemIndex) => itemIndex !== index))}>×</button>
                </div>)}
                {requestedAttachments.map((file, index) => <div className="public-chat-file-chip" key={`attachment-${index}-${file.name}-${file.size}`}>
                  <span className="public-chat-file-chip-icon" aria-hidden="true">⌕</span>
                  <span className="public-chat-file-chip-name">{file.name}</span>
                  <button type="button" aria-label={`Remove ${file.name}`} disabled={busy} onClick={() => setRequestedAttachments(files => files.filter((_, itemIndex) => itemIndex !== index))}>×</button>
                </div>)}
              </div>}

              {error && <div className="card error public-chat-error">{error}</div>}

              <div className="public-chat-compose-row">
                <div className="public-chat-add-wrap">
                  <button
                    type="button"
                    className="public-chat-add-button"
                    aria-label="Add image or attachment"
                    aria-expanded={attachmentMenuOpen}
                    disabled={busy}
                    onClick={() => setAttachmentMenuOpen(open => !open)}
                  >+</button>
                  {attachmentMenuOpen && <div className="public-chat-add-menu" role="menu">
                    <button type="button" role="menuitem" disabled={busy} onClick={() => { setAttachmentMenuOpen(false); cameraInputRef.current?.click(); }}>
                      <span aria-hidden="true">📷</span><span><strong>Take photo</strong><small>Open your device camera</small></span>
                    </button>
                    <button type="button" role="menuitem" disabled={busy} onClick={() => { setAttachmentMenuOpen(false); imageInputRef.current?.click(); }}>
                      <span aria-hidden="true">▧</span><span><strong>Add images</strong><small>JPEG, PNG, GIF or WebP</small></span>
                    </button>
                    <button type="button" role="menuitem" disabled={busy} onClick={() => { setAttachmentMenuOpen(false); attachmentInputRef.current?.click(); }}>
                      <span aria-hidden="true">⌕</span><span><strong>Add files</strong><small>Up to 25 MB each</small></span>
                    </button>
                  </div>}
                  <input
                    ref={cameraInputRef}
                    className="public-chat-hidden-input"
                    type="file"
                    accept="image/*"
                    capture="environment"
                    aria-label="Take photo with camera"
                    disabled={busy}
                    onChange={event => {
                      const photos = Array.from(event.target.files || []);
                      setRequestedImages(current => [...current, ...photos]);
                      event.currentTarget.value = '';
                    }}
                  />
                  <input
                    ref={imageInputRef}
                    className="public-chat-hidden-input"
                    type="file"
                    accept="image/jpeg,image/png,image/gif,image/webp"
                    multiple
                    disabled={busy}
                    onChange={event => {
                      const files = Array.from(event.target.files || []);
                      setRequestedImages(current => [...current, ...files]);
                      event.currentTarget.value = '';
                    }}
                  />
                  <input
                    ref={attachmentInputRef}
                    className="public-chat-hidden-input"
                    type="file"
                    multiple
                    disabled={busy}
                    onChange={event => {
                      const files = Array.from(event.target.files || []);
                      setRequestedAttachments(current => [...current, ...files]);
                      event.currentTarget.value = '';
                    }}
                  />
                </div>
                <label className="public-chat-message-box">
                  <textarea
                    aria-label="Message"
                    value={requestedInformation}
                    maxLength={4000}
                    rows={1}
                    autoFocus
                    disabled={busy}
                    onChange={event => setRequestedInformation(event.target.value)}
                    onKeyDown={event => {
                      if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault();
                        if (!busy && effectiveSignature && (requestedInformation.trim() || requestedImages.length || requestedAttachments.length)) {
                          chooseAction('requested_info', requestedInformation, requestedImages, requestedAttachments);
                        }
                      }
                    }}
                    placeholder="Message ALS Edmonton…"
                  />
                </label>
                <button
                  className="public-chat-send-button"
                  type="button"
                  aria-label={!requestedInformation.trim() && requestedImages.length ? 'Send photo' : 'Send message'}
                  disabled={busy || !effectiveSignature || (!requestedInformation.trim() && !requestedImages.length && !requestedAttachments.length)}
                  onClick={() => chooseAction('requested_info', requestedInformation, requestedImages, requestedAttachments)}
                >{busy ? <span className="public-chat-send-busy">…</span> : <span aria-hidden="true">➤</span>}</button>
              </div>
              <div className="public-chat-compose-help">
                <span>{requestedInformation.length}/4000</span>
                <span>Photos can be sent without text · Shift+Enter for a new line</span>
              </div>
            </div>
          </aside>
        </div>}

    </section>
  </main>;
}
