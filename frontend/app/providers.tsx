'use client';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import React from 'react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { api, getToken, setToken } from '@/lib/api';
import { useUiStore } from '@/state/uiStore';

const NAV = [
  { label: 'Monitor', links: [
    { href: '/dashboard', label: 'Command centre' },
    { href: '/works', label: 'Works explorer' },
    { href: '/alerts', label: 'Alerts' },
  ] },
  { label: 'Verify', links: [
    { href: '/cases', label: 'Cases' },
    { href: '/verification', label: 'Verification workspace' },
  ] },
  { label: 'Understand', links: [
    { href: '/analytics', label: 'Analytics' },
    { href: '/data-quality', label: 'Data quality' },
    { href: '/ingestion', label: 'Ingestion' },
  ] },
  { label: 'Govern', links: [
    { href: '/admin/rules', label: 'Rules and weights' },
    { href: '/admin/users', label: 'Users and roles' },
    { href: '/audit', label: 'Audit trail' },
    { href: '/settings', label: 'Settings' },
  ] },
];

type Me = { full_name: string; role: string; role_label: string; permissions: string[]; state?: string | null; district?: string | null };

function GlobalSearch() {
  const router = useRouter();
  const [term, setTerm] = React.useState('');
  const [debounced, setDebounced] = React.useState('');
  React.useEffect(() => {
    const timer = setTimeout(() => setDebounced(term.trim()), 350);
    return () => clearTimeout(timer);
  }, [term]);
  const { data } = useQuery({
    queryKey: ['search', debounced],
    queryFn: () => api.get<{ works: Array<{ work_id: string; description?: string }>; cases: Array<{ case_ref: string; work_id: string }> }>('/search?q=' + encodeURIComponent(debounced)),
    enabled: debounced.length >= 2,
  });
  return (
    <div className="stack" style={{ position: 'relative', minWidth: 'min(100%, 18rem)' }}>
      <label className="field">
        <span className="visually-hidden">Search works and cases</span>
        <input value={term} onChange={(event) => setTerm(event.target.value)} placeholder="Search work ID, description, case" type="search" />
      </label>
      {data && debounced.length >= 2 ? (
        <div className="panel" style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 20 }}>
          <div className="panel-body stack">
            {data.works.length === 0 && data.cases.length === 0 ? <span className="muted">No matches</span> : null}
            {data.works.slice(0, 5).map((work) => (
              <button key={work.work_id} type="button" className="btn" onClick={() => { setTerm(''); router.push('/works/' + work.work_id); }}>
                {work.work_id} - {work.description?.slice(0, 46) || ''}
              </button>
            ))}
            {data.cases.slice(0, 5).map((item) => (
              <button key={item.case_ref} type="button" className="btn" onClick={() => { setTerm(''); router.push('/cases/' + item.case_ref); }}>
                {item.case_ref} - {item.work_id}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { sidebarOpen, setSidebarOpen } = useUiStore();
  const [ready, setReady] = React.useState(false);

  React.useEffect(() => {
    if (!getToken()) router.replace('/login');
    else setReady(true);
  }, [router]);

  const me = useQuery({ queryKey: ['me'], queryFn: () => api.get<Me>('/me'), enabled: ready });
  const alerts = useQuery({
    queryKey: ['alerts', 'unread'],
    queryFn: () => api.get<{ unread: number }>('/notifications?unread_only=true'),
    enabled: ready,
    refetchInterval: 60000,
  });

  if (!ready) return null;

  return (
    <div className="app-shell">
      <nav className="sidebar" data-open={sidebarOpen} aria-label="Primary">
        <span className="brand">DRISHTI<small>MPLADS risk and verification</small></span>
        {NAV.map((group) => (
          <div key={group.label}>
            <p className="nav-group-label">{group.label}</p>
            {group.links.map((link) => (
              <Link key={link.href} href={link.href} className="nav-link" onClick={() => setSidebarOpen(false)}
                aria-current={pathname === link.href || pathname.startsWith(link.href + '/') ? 'page' : undefined}>
                {link.label}
                {link.href === '/alerts' && alerts.data?.unread ? ' (' + alerts.data.unread + ')' : ''}
              </Link>
            ))}
          </div>
        ))}
        <p className="muted" style={{ color: '#8fa1b6', marginTop: 'auto' }}>Risk is not a fraud verdict. Risk is a reason to verify.</p>
      </nav>
      <div className="main">
        <header className="topbar">
          <button type="button" className="btn menu-toggle" onClick={() => setSidebarOpen(!sidebarOpen)} aria-expanded={sidebarOpen}>Menu</button>
          <GlobalSearch />
          <div className="row">
            <span className="muted nowrap">
              {me.data ? me.data.full_name + ' - ' + me.data.role_label : 'Loading account'}
              {me.data?.district ? ' (' + me.data.district + ')' : me.data?.state ? ' (' + me.data.state + ')' : ''}
            </span>
            <button type="button" className="btn" onClick={async () => {
              try { await api.post('/auth/logout'); } finally { setToken(null); router.replace('/login'); }
            }}>Sign out</button>
          </div>
        </header>
        <main id="main-content" className="content">{children}</main>
      </div>
    </div>
  );
}

export function Providers({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [client] = React.useState(() => new QueryClient({
    defaultOptions: { queries: { staleTime: 30000, retry: 1, refetchOnWindowFocus: false } },
  }));
  const bare = pathname === '/login';
  return (
    <QueryClientProvider client={client}>
      {bare ? children : <Shell>{children}</Shell>}
    </QueryClientProvider>
  );
}
