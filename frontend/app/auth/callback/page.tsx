'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';

/** Microsoft Entra Web redirect; backend exchanges the code with PKCE. */
export default function MicrosoftCallbackPage() {
  const [status, setStatus] = useState('Connecting your Microsoft 365 account…');
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code') || '';
    const state = params.get('state') || '';
    const denied = params.get('error');
    // Immediately remove OAuth code from address bar and browser history.
    window.history.replaceState(null, '', '/auth/callback');
    if (denied || !code || !state) {
      setStatus('Microsoft connection was canceled or denied. No tracker settings were changed.');
      return;
    }
    api('/auth/microsoft/callback/', {
      method: 'POST', body: JSON.stringify({ code, state }),
    }).then(() => { setConnected(true); setStatus('Microsoft 365 connected. You can now send emails directly from ALS Ticket Tracker.'); })
      .catch(error => setStatus(error instanceof Error ? error.message : 'Microsoft connection failed.'));
  }, []);
  return <main style={{maxWidth:620, margin:'8vh auto', padding:24}}>
    <section className="panel panel-blue"><div className="panel-header">Microsoft 365 Mail Connection</div>
      <div className="panel-body stack"><p role="status">{status}</p>
        <p className="muted">Your regular ALS Ticket Tracker sign-in remains separate.</p>
        <Link href="/account" className="button">{connected ? 'Go to My Account' : 'Back to My Account'}</Link>
      </div></section>
  </main>;
}
