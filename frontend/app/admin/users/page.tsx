'use client';
import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, formatDateTime } from '@/lib/api';
import { DataTable, ErrorState, Panel, Skeleton } from '@/components/ui';

type UserRow = { id: number; email: string; full_name: string; role: string; role_label: string; state?: string | null; district?: string | null; is_active: boolean; last_login_at?: string | null };

export default function UsersPage() {
  const client = useQueryClient();
  const [feedback, setFeedback] = React.useState<string | null>(null);
  const [form, setForm] = React.useState({ email: '', full_name: '', role: 'REVIEWER', password: '', state: '', district: '' });

  const query = useQuery({ queryKey: ['users'], queryFn: () => api.get<{ users: UserRow[]; roles: string[] }>('/admin/users') });
  const invalidate = () => client.invalidateQueries({ queryKey: ['users'] });
  const fail = (error: unknown) => setFeedback(error instanceof Error ? error.message : 'That action could not be completed.');

  const create = useMutation({
    mutationFn: () => api.post('/admin/users', {
      email: form.email, full_name: form.full_name, role: form.role, password: form.password,
      state: form.state || null, district: form.district || null,
    }),
    onSuccess: () => { setFeedback('User created.'); setForm({ email: '', full_name: '', role: 'REVIEWER', password: '', state: '', district: '' }); invalidate(); },
    onError: fail,
  });
  const update = useMutation({
    mutationFn: (payload: { id: number; body: Record<string, unknown> }) => api.patch('/admin/users/' + payload.id, payload.body),
    onSuccess: invalidate, onError: fail,
  });

  if (query.isLoading) return <Skeleton rows={8} />;
  if (query.error) return <ErrorState error={query.error} retry={() => query.refetch()} />;
  const data = query.data!;

  return (
    <>
      <h1>Users and roles</h1>
      {feedback ? <p className="notice" role="status">{feedback}</p> : null}
      <Panel title="Add a user" description="Roles are enforced in the API, not only in the navigation.">
        <div className="filter-bar">
          <label className="field">Email<input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></label>
          <label className="field">Full name<input value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} /></label>
          <label className="field">Role
            <select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}>
              {data.roles.map((role) => <option key={role} value={role}>{role}</option>)}
            </select>
          </label>
          <label className="field">Temporary password<input type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} /></label>
          <label className="field">State<input value={form.state} onChange={(event) => setForm({ ...form, state: event.target.value })} /></label>
          <label className="field">District<input value={form.district} onChange={(event) => setForm({ ...form, district: event.target.value })} /></label>
        </div>
        <button type="button" className="btn btn--primary" disabled={!form.email || !form.full_name || form.password.length < 8 || create.isPending}
          onClick={() => create.mutate()}>Create user</button>
        <p className="muted">Passwords are stored as PBKDF2-SHA256 hashes and are never logged.</p>
      </Panel>
      <Panel title="Accounts">
        <DataTable caption="Users" rows={data.users} rowKey={(row) => row.id}
          columns={[
            { key: 'name', header: 'Name', render: (row) => <div className="wrap">{row.full_name}<p className="muted mono">{row.email}</p></div> },
            { key: 'role', header: 'Role', render: (row) => (
              <select value={row.role} aria-label={'Role for ' + row.full_name}
                onChange={(event) => update.mutate({ id: row.id, body: { role: event.target.value } })}>
                {data.roles.map((role) => <option key={role} value={role}>{role}</option>)}
              </select>
            ) },
            { key: 'scope', header: 'Scope', render: (row) => [row.district, row.state].filter(Boolean).join(', ') || 'All' },
            { key: 'active', header: 'Active', render: (row) => (
              <input type="checkbox" checked={row.is_active} aria-label={'Active for ' + row.full_name}
                onChange={(event) => update.mutate({ id: row.id, body: { is_active: event.target.checked } })} />
            ) },
            { key: 'login', header: 'Last sign in', render: (row) => formatDateTime(row.last_login_at) },
          ]} />
      </Panel>
    </>
  );
}
