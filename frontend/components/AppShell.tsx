'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { api, clearToken, getToken } from '@/lib/api';
import { ProblemTable } from '@/lib/problemTables';
import RequiredRoleModal from '@/components/RequiredRoleModal';

type User = { id: number; username: string; email: string; first_name: string; last_name: string; name: string; role: string; role_label: string; needs_role: boolean; is_admin: boolean };
type IconName = 'samples' | 'customers' | 'logout' | 'table' | 'settings' | 'account' | 'chevron' | 'container' | 'shipping' | 'flask' | 'clock' | 'create';

function Icon({ name }: { name: IconName }) {
  const common = { width: 20, height: 20, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
  if (name === 'samples') return <svg {...common}><path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/></svg>;
  if (name === 'customers') return <svg {...common}><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/></svg>;
  if (name === 'account') return <svg {...common}><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>;
  if (name === 'table') return <svg {...common}><rect x="3" y="4" width="18" height="16" rx="1"/><path d="M3 9h18M9 4v16"/></svg>;
  if (name === 'container') return <svg {...common}><path d="M4 7h16l-1 13H5L4 7z"/><path d="M3 4h18v3H3z"/><path d="M9 11h6"/></svg>;
  if (name === 'shipping') return <svg {...common}><path d="M3 7h11v10H3z"/><path d="M14 10h4l3 3v4h-7z"/><circle cx="7" cy="19" r="2"/><circle cx="18" cy="19" r="2"/></svg>;
  if (name === 'flask') return <svg {...common}><path d="M9 3h6"/><path d="M10 3v6l-5 9a2 2 0 0 0 1.74 3h10.52A2 2 0 0 0 19 18l-5-9V3"/><path d="M7.5 15h9"/></svg>;
  if (name === 'clock') return <svg {...common}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>;
  if (name === 'create') return <svg {...common}><path d="M12 5v14"/><path d="M5 12h14"/><rect x="3" y="3" width="18" height="18" rx="3"/></svg>;
  if (name === 'settings') return <svg {...common}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21H9.6v-.1a1.7 1.7 0 0 0-1.1-1.55 1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3V9.6h.1A1.7 1.7 0 0 0 4.65 8.5a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3h4v.1A1.7 1.7 0 0 0 15.5 4.65a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.16.37.39.71.7 1 .3.29.69.43 1.1.4h.1v4h-.1c-.68-.01-1.29.39-1.55 1z"/></svg>;
  if (name === 'chevron') return <svg {...common}><path d="M9 18l6-6-6-6"/></svg>;
  return <svg {...common}><path d="M10 17l5-5-5-5"/><path d="M15 12H3"/><path d="M21 19V5a2 2 0 0 0-2-2h-6"/></svg>;
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [tables, setTables] = useState<ProblemTable[]>([]);
  const [problemSamplesOpen, setProblemSamplesOpen] = useState(false);
  const [disposalOpen, setDisposalOpen] = useState(false);
  const [shippingOpen, setShippingOpen] = useState(false);
  const [backToTestingOpen, setBackToTestingOpen] = useState(false);

  useEffect(() => {
    const publicRoute = pathname === '/login' || pathname.startsWith('/login/') || pathname.startsWith('/acknowledge/') || pathname.startsWith('/track/');
    if (publicRoute) return;
    if (!getToken()) {
      router.replace('/login');
      return;
    }
    api('/auth/me/').then((u:User) => {
      setUser(u);
      if (u.needs_role && pathname !== '/account') router.push('/account');
    }).catch(() => {
      clearToken();
      setUser(null);
      router.replace('/login');
    });
    api('/problem-tables/').then(d => setTables(Array.isArray(d) ? d : (d.results || []))).catch(()=>{});
  }, [pathname, router]);

  if (pathname === '/login' || pathname.startsWith('/login/') || pathname.startsWith('/acknowledge/') || pathname.startsWith('/track/')) return <>{children}</>;

  async function logout() {
    try { if (getToken()) await api('/auth/logout/', { method: 'POST', successMessage:'Signed out successfully.', errorMessage:'Could not sign out cleanly' }); } catch {}
    clearToken(); setUser(null); router.push('/login');
  }

  return <div className={`admin-shell ${collapsed ? 'sidebar-collapsed' : ''}`}>
    <aside className="sidebar">
      <Link href="/" className="sidebar-brand"><span className="brand-mark">E</span><span className="brand-label">Edmonton Problem Sample Tracker</span></Link>
      <Link href="/account" className="user-panel user-panel-link"><div className="avatar">{(user?.name || user?.username || 'U').charAt(0).toUpperCase()}</div><div className="user-copy"><div className="user-name">{user?.name || 'ALS User'}</div><div className="user-role">{user?.is_admin ? 'Administrator' : (user?.role_label || 'Choose role')}</div><div className="user-email">{user?.username ? `@${user.username}` : 'Sign in required'}</div></div></Link>
      <nav className="side-nav" aria-label="Main navigation">
        <div className="side-section-label">Workflows</div>

        <Link href="/create-problem-sample" className={`side-link ${pathname === '/create-problem-sample' || pathname === '/problems/new' ? 'active' : ''}`}>
          <span className="side-icon"><Icon name="create"/></span><span className="side-label">Create Problem Sample</span>
        </Link>

        <Link href="/follow-up-required" className={`side-link ${pathname === '/follow-up-required' ? 'active' : ''}`}>
          <span className="side-icon"><Icon name="clock"/></span><span className="side-label">Follow Up Required</span>
        </Link>

        <div className="side-group">
          <button
            type="button"
            className={`side-link side-group-toggle ${pathname.startsWith('/disposal') ? 'active' : ''}`}
            aria-expanded={disposalOpen}
            onClick={() => setDisposalOpen(v => !v)}
          >
            <span className="side-icon"><Icon name="container"/></span>
            <span className="side-label">Disposal</span>
            <span className={`side-group-chevron ${disposalOpen ? 'open' : ''}`} aria-hidden="true"><Icon name="chevron"/></span>
          </button>
          {disposalOpen && (
            <div className="side-subnav container-side-subnav">
              <Link href="/disposal/containers" className={`side-link table-side-link ${pathname.startsWith('/disposal/containers') ? 'active' : ''}`}>
                <span className="side-icon"><Icon name="container"/></span><span className="side-label">Dispose Containers</span>
              </Link>
              <Link href="/disposal/samples" className={`side-link table-side-link ${pathname === '/disposal/samples' ? 'active' : ''}`}>
                <span className="side-icon"><Icon name="samples"/></span><span className="side-label">Dispose Samples</span>
              </Link>
            </div>
          )}
        </div>

        <div className="side-group">
          <button
            type="button"
            className={`side-link side-group-toggle ${pathname.startsWith('/shipping') ? 'active' : ''}`}
            aria-expanded={shippingOpen}
            onClick={() => setShippingOpen(v => !v)}
          >
            <span className="side-icon"><Icon name="shipping"/></span>
            <span className="side-label">Shipping</span>
            <span className={`side-group-chevron ${shippingOpen ? 'open' : ''}`} aria-hidden="true"><Icon name="chevron"/></span>
          </button>
          {shippingOpen && (
            <div className="side-subnav shipping-side-subnav">
              <Link href="/shipping/to-be-shipped" className={`side-link table-side-link ${pathname === '/shipping/to-be-shipped' ? 'active' : ''}`}>
                <span className="side-icon"><Icon name="shipping"/></span><span className="side-label">To be shipped</span>
              </Link>
            </div>
          )}
        </div>

        <div className="side-group">
          <button
            type="button"
            className={`side-link side-group-toggle ${pathname.startsWith('/back-to-testing') ? 'active' : ''}`}
            aria-expanded={backToTestingOpen}
            onClick={() => setBackToTestingOpen(v => !v)}
          >
            <span className="side-icon"><Icon name="flask"/></span>
            <span className="side-label">Back To Testing</span>
            <span className={`side-group-chevron ${backToTestingOpen ? 'open' : ''}`} aria-hidden="true"><Icon name="chevron"/></span>
          </button>
          {backToTestingOpen && (
            <div className="side-subnav shipping-side-subnav">
              <Link href="/back-to-testing/to-be-back-to-testing" className={`side-link table-side-link ${pathname === '/back-to-testing/to-be-back-to-testing' ? 'active' : ''}`}>
                <span className="side-icon"><Icon name="flask"/></span><span className="side-label">To be back to testing</span>
              </Link>
            </div>
          )}
        </div>

        <div className="side-section-label">Tables</div>

        <div className="side-group">
          <button
            type="button"
            className={`side-link side-group-toggle ${pathname === '/' ? 'active' : ''}`}
            aria-expanded={problemSamplesOpen}
            onClick={() => setProblemSamplesOpen(v => !v)}
          >
            <span className="side-icon"><Icon name="samples"/></span>
            <span className="side-label">Problem Samples</span>
            <span className={`side-group-chevron ${problemSamplesOpen ? 'open' : ''}`} aria-hidden="true"><Icon name="chevron"/></span>
          </button>
          {problemSamplesOpen && (
            <div className="side-subnav">
              {tables.length ? tables.map(t => (
                <Link key={t.id} href={`/?table=${t.id}`} className="side-link table-side-link">
                  <span className="side-icon"><Icon name="table"/></span>
                  <span className="side-label">{t.name}</span>
                </Link>
              )) : (
                <div className="side-empty-label">No problem sample tables</div>
              )}
            </div>
          )}
        </div>

        <Link href="/tables" className={`side-link ${pathname.startsWith('/tables')?'active':''}`}>
          <span className="side-icon"><Icon name="settings"/></span><span className="side-label">Manage Tables</span>
        </Link>

        <div className="side-section-label">Settings</div>

        <Link href="/customers" className={`side-link ${pathname==='/customers'?'active':''}`}>
          <span className="side-icon"><Icon name="customers"/></span><span className="side-label">Customers</span>
        </Link>
        {user?.is_admin && <Link href="/accounts" className={`side-link ${pathname==='/accounts'?'active':''}`}>
          <span className="side-icon"><Icon name="account"/></span><span className="side-label">User Accounts</span>
        </Link>}
        <Link href="/account" className={`side-link ${pathname==='/account'?'active':''}`}>
          <span className="side-icon"><Icon name="account"/></span><span className="side-label">My Account</span>
        </Link>
        <button type="button" className="side-link side-button" onClick={logout}>
          <span className="side-icon logout-icon"><Icon name="logout"/></span><span className="side-label">Logout</span>
        </button>
      </nav>
    </aside>
    <div className="main-column"><header className="admin-topbar"><button className="menu-toggle" type="button" aria-label="Toggle sidebar" onClick={()=>setCollapsed(v=>!v)}><span></span><span></span><span></span></button><div className="topbar-title">Edmonton Problem Sample Tracker</div></header><main className="page-content">{children}</main></div>
    {user?.needs_role && <RequiredRoleModal user={user} onSaved={setUser} />}
  </div>;
}
