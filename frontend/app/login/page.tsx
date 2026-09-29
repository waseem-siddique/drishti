'use client';
import { useRouter } from 'next/navigation';
import React from 'react';
import { api, setToken } from '@/lib/api';

const DEMO = [
  ['admin@drishti.local', 'Administrator'],
  ['ministry@drishti.local', 'Ministry / national'],
  ['state@drishti.local', 'State nodal officer'],
  ['district@drishti.local', 'District officer'],
  ['reviewer@drishti.local', 'Reviewer'],
  ['auditor@drishti.local', 'Auditor (read only)'],
];

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = React.useState('admin@drishti.local');
  const [password, setPassword] = React.useState('Drishti@2026');
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api.post<{ token: string }>('/auth/login', { email, password });
      setToken(result.token);
      router.replace('/dashboard');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Sign in failed.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submit}>
        <h1>DRISHTI</h1>
        <p className="muted">Turning thousands of scheme records into prioritized, explainable verification cases.</p>
        {error ? <p className="error-state" role="alert">{error}</p> : null}
        <label className="field">Work email
          <input type="email" value={email} autoComplete="username" required onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label className="field">Password
          <input type="password" value={password} autoComplete="current-password" required onChange={(event) => setPassword(event.target.value)} />
        </label>
        <button type="submit" className="btn btn--primary" disabled={busy}>{busy ? 'Signing in' : 'Sign in'}</button>
        <fieldset className="stack" style={{ border: '1px solid var(--line)', borderRadius: 4 }}>
          <legend className="muted">Demo accounts (password Drishti@2026)</legend>
          {DEMO.map(([value, label]) => (
            <button key={value} type="button" className="btn" onClick={() => { setEmail(value); setPassword('Drishti@2026'); }}>
              {label} - {value}
            </button>
          ))}
        </fieldset>
        <p className="transparency-note">DRISHTI provides risk-based decision support. A risk score does not establish fraud or misconduct. Final determination requires authorized human verification.</p>
      </form>
    </div>
  );
}
