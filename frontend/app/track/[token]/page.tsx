'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';
const TRACKING_API = `${API}/public/problem-sample-tracking`;

type CustomerAction = '' | 'dispose' | 'ship_back' | 'hold' | 'requested_info';

type PublicImage = { id: number; name: string; size_bytes: number };
type PublicAttachment = { id: number; name: string; size_bytes: number; content_type?: string };
type PublicDetail = { label: string; value: string };

type TrackingState = {
  state: 'pending' | 'acknowledged' | 'disposing' | 'shipping' | 'testing' | 'dumped' | 'expired';
  message: string;
  problem_number?: number;
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
};

function formatFileSize(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(kb >= 10 ? 0 : 1)} KB`;
  const mb = kb / 1024;
  return `${mb.toFixed(mb >= 10 ? 0 : 1)} MB`;
}

const actionLabels: Record<Exclude<CustomerAction, ''>, string> = {
  dispose: 'Dispose Sample(s)',
  ship_back: 'Ship back samples',
  hold: 'Hold sample',
  requested_info: 'Fill out requested information (if applicable)',
};

export default function ProblemSampleTrackingPage() {
  const { token } = useParams<{ token: string }>();
  const [data, setData] = useState<TrackingState | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [signature, setSignature] = useState('');
  const [requestedInfoOpen, setRequestedInfoOpen] = useState(false);
  const [requestedInformation, setRequestedInformation] = useState('');

  async function load() {
    setError('');
    const response = await fetch(`${TRACKING_API}/${token}/`, { cache: 'no-store' });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || 'Could not open the problem sample tracking link.');
    setData(body);
  }

  useEffect(() => {
    load().catch(error => setError(error instanceof Error ? error.message : 'Could not open the problem sample tracking link.'));
  }, [token]);

  async function chooseAction(action: Exclude<CustomerAction, ''>, requestedInfo = '') {
    const signedName = signature.trim();
    if (busy || !signedName) return;
    setBusy(true);
    setError('');
    try {
      const response = await fetch(`${TRACKING_API}/${token}/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, signature: signedName, requested_information: requestedInfo.trim() }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || 'Your selection could not be recorded.');
      setData(body);
      setSignature('');
      setRequestedInformation('');
      setRequestedInfoOpen(false);
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Your selection could not be recorded.');
    } finally {
      setBusy(false);
    }
  }

  return <main className="public-ack-page">
    <section className="public-ack-card">
      <img src="/als-logo.png" alt="ALS" className="public-ack-logo" />
      <div className="eyebrow">Problem Sample Tracking</div>
      {error && !data ? <><h1>Unable to open link</h1><div className="card error">{error}</div></> : !data ? <h1>Loading…</h1> : <>
        <h1>{data.message}</h1>
        {data.problem_number && <div className="public-ack-problem">Problem ID #{data.problem_number}</div>}

        {(data.details?.length || 0) > 0 && <section className="public-tracking-details">
          <h2>Problem Sample Details</h2>
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
            <p>Files provided with this problem sample are available while this problem sample tracking link is active.</p>
          </div>
          {(data.images?.length || 0) > 0 && <div className="public-ack-images">
            {data.images!.map(image => {
              const imageUrl = `${TRACKING_API}/${token}/images/${image.id}/`;
              return <a key={image.id} className="public-ack-image-card" href={imageUrl} target="_blank" rel="noreferrer">
                <img src={imageUrl} alt={image.name || `Problem sample image ${image.id}`} loading="lazy" />
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
          <p>Selecting an option records your requested action for this problem sample.</p>
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
          <div className="public-ack-action-buttons">
            {data.automatic_disposal_active ? <>
              <button className="button" disabled={busy || !signature.trim()} onClick={() => chooseAction('hold')}>Stop eventual disposal</button>
              <button className="button secondary" disabled={busy || !signature.trim()} onClick={() => chooseAction('dispose')}>Permit immediate disposal</button>
              <button className="button secondary" disabled={busy || !signature.trim()} onClick={() => { setRequestedInformation(''); setRequestedInfoOpen(true); }}>Fill out requested information (if applicable)</button>
              <button className="button secondary" disabled={busy || !signature.trim()} onClick={() => chooseAction('ship_back')}>Ship back</button>
            </> : <>
              <button className="button" disabled={busy || !signature.trim()} onClick={() => chooseAction('dispose')}>Permit immediate disposal</button>
              <button className="button secondary" disabled={busy || !signature.trim()} onClick={() => { setRequestedInformation(''); setRequestedInfoOpen(true); }}>Fill out requested information (if applicable)</button>
              <button className="button secondary" disabled={busy || !signature.trim()} onClick={() => chooseAction('ship_back')}>Ship back</button>
            </>}
          </div>
        </div>}
        {data.state === 'acknowledged' && !data.can_choose_action && data.customer_action && <div className="public-ack-selection">
          Your response has been recorded: <strong>{data.customer_action_label || actionLabels[data.customer_action]}</strong>.
        </div>}
        {data.state === 'disposing' && <p>ALS has recorded that the sample(s) are marked for disposal.</p>}
        {data.state === 'shipping' && <p>ALS has recorded that the sample(s) are to be shipped back to the client.</p>}
        {data.state === 'testing' && <p>ALS has recorded that the sample(s) are being returned to testing.</p>}
        {data.state === 'dumped' && <p>This problem sample has been disposed. No customer action is available.</p>}
        {data.state === 'expired' && <p>This problem sample tracking link is no longer active.</p>}
      </>}

        {requestedInfoOpen && <div className="public-requested-info-overlay" role="presentation" onMouseDown={event => {
          if (event.target === event.currentTarget && !busy) setRequestedInfoOpen(false);
        }}>
          <div className="public-requested-info-dialog" role="dialog" aria-modal="true" aria-labelledby="requested-info-title" aria-describedby="requested-info-description">
            <h2 id="requested-info-title">Fill out requested information</h2>
            <p id="requested-info-description">Provide the information ALS requested about this problem sample. This message will be saved with your signed response.</p>
            <label className="public-requested-info-field">
              <span>Information about the problem sample <strong aria-hidden="true">*</strong></span>
              <textarea
                value={requestedInformation}
                maxLength={4000}
                rows={7}
                autoFocus
                disabled={busy}
                onChange={event => setRequestedInformation(event.target.value)}
                placeholder="Type the requested information here…"
              />
              <small>{requestedInformation.length}/4000 characters</small>
            </label>
            <div className="public-requested-info-signature">Signed by <strong>{signature.trim()}</strong></div>
            <div className="public-requested-info-actions">
              <button className="button secondary" type="button" disabled={busy} onClick={() => { setRequestedInfoOpen(false); setRequestedInformation(''); }}>Cancel</button>
              <button className="button" type="button" disabled={busy || !requestedInformation.trim()} onClick={() => chooseAction('requested_info', requestedInformation)}>{busy ? 'Sending…' : 'Send response'}</button>
            </div>
          </div>
        </div>}

    </section>
  </main>;
}
