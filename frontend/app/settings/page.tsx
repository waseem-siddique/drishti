'use client';
import { useQuery } from '@tanstack/react-query';
import { api, API_BASE } from '@/lib/api';
import { DataTable, ErrorState, Panel, Skeleton, TransparencyNote } from '@/components/ui';

type Me = { full_name: string; email: string; role_label: string; state?: string | null; district?: string | null; permissions: string[] };
type Health = { engine_version: string; ontology_version: string; environment: string; llm: { provider?: string; model?: string; enabled?: boolean }; transparency_note: string };
type Integrations = { adapters: Array<{ key: string; name: string; status: string; note: string; capabilities?: string[] }>; note: string };

export default function SettingsPage() {
  const me = useQuery({ queryKey: ['me'], queryFn: () => api.get<Me>('/me') });
  const health = useQuery({ queryKey: ['health'], queryFn: async () => (await fetch(API_BASE + '/api/health')).json() as Promise<Health> });
  const integrations = useQuery({ queryKey: ['integrations'], queryFn: () => api.get<Integrations>('/integrations') });

  return (
    <>
      <h1>Settings</h1>
      <Panel title="Your access">
        {me.isLoading ? <Skeleton /> : me.error ? <ErrorState error={me.error} /> : me.data ? (
          <div className="stack">
            <p><strong>{me.data.full_name}</strong> <span className="muted mono">{me.data.email}</span></p>
            <p className="muted">Role: {me.data.role_label} - scope: {[me.data.district, me.data.state].filter(Boolean).join(', ') || 'All states'}</p>
            <h3>Permissions</h3>
            <p className="mono">{me.data.permissions.join(', ')}</p>
          </div>
        ) : null}
      </Panel>

      <Panel title="Engine and model governance" description="Model configuration is environment-driven and never used to compute risk.">
        {health.isLoading ? <Skeleton /> : health.error ? <ErrorState error={health.error} /> : health.data ? (
          <div className="stack">
            <p className="muted">Environment {health.data.environment} - engine {health.data.engine_version} - ontology {health.data.ontology_version}</p>
            <p className="muted">
              Language model: {health.data.llm?.provider || 'none'} / {health.data.llm?.model || 'none'} -{' '}
              {health.data.llm?.enabled ? 'available for narration only' : 'not configured; deterministic explanations are used'}
            </p>
            <TransparencyNote note={health.data.transparency_note} />
          </div>
        ) : null}
      </Panel>

      <Panel title="External systems" description="These adapters are integration-ready. None of them is connected.">
        {integrations.isLoading ? <Skeleton /> : integrations.error ? <ErrorState error={integrations.error} /> : integrations.data ? (
          <>
            <DataTable caption="Integration adapters" rows={integrations.data.adapters} rowKey={(row) => row.key}
              columns={[
                { key: 'name', header: 'System', render: (row) => row.name },
                { key: 'status', header: 'Status', render: (row) => row.status },
                { key: 'note', header: 'Note', render: (row) => <span className="wrap">{row.note}</span> },
              ]} />
            <p className="notice notice--warn">{integrations.data.note}</p>
          </>
        ) : null}
      </Panel>
    </>
  );
}
