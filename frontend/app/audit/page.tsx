'use client';
import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, formatDateTime } from '@/lib/api';
import { DataTable, EmptyState, ErrorState, Panel, Skeleton } from '@/components/ui';

type Entry = {
  id: number; action: string; actor?: string | null; entity_type?: string | null; entity_ref?: string | null;
  previous_value?: unknown; new_value?: unknown; ip_address?: string | null; created_at: string;
};

export default function AuditPage() {
  const [action, setAction] = React.useState('');
  const [entityRef, setEntityRef] = React.useState('');
  const [page, setPage] = React.useState(1);

  const params = new URLSearchParams({ page: String(page), page_size: '50' });
  if (action) params.set('action', action);
  if (entityRef) params.set('entity_ref', entityRef);

  const query = useQuery({
    queryKey: ['audit', params.toString()],
    queryFn: () => api.get<{ items: Entry[]; total: number; pages: number; actions: string[] }>('/admin/audit?' + params.toString()),
  });

  return (
    <>
      <h1>Audit trail</h1>
      <Panel title="Recorded actions" description="Every state change records who did it, when, and the previous and new value."
        actions={
          <>
            <label className="field">Action
              <select value={action} onChange={(event) => { setAction(event.target.value); setPage(1); }}>
                <option value="">All</option>
                {(query.data?.actions || []).map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <label className="field">Entity reference
              <input value={entityRef} onChange={(event) => { setEntityRef(event.target.value); setPage(1); }} placeholder="MPL-10427 or VC-2026-00001" />
            </label>
          </>
        }>
        {query.isLoading ? <Skeleton rows={8} /> : query.error ? <ErrorState error={query.error} retry={() => query.refetch()} />
          : !query.data?.items.length ? <EmptyState title="No audit entries match" />
          : (
            <>
              <DataTable caption="Audit log" rows={query.data.items} rowKey={(row) => row.id}
                columns={[
                  { key: 'at', header: 'When', render: (row) => <span className="nowrap">{formatDateTime(row.created_at)}</span> },
                  { key: 'actor', header: 'Actor', render: (row) => row.actor || 'System' },
                  { key: 'action', header: 'Action', render: (row) => <span className="mono">{row.action}</span> },
                  { key: 'entity', header: 'Entity', render: (row) => (row.entity_type || '-') + ' ' + (row.entity_ref || '') },
                  { key: 'before', header: 'Previous value', render: (row) => <span className="wrap mono">{row.previous_value ? JSON.stringify(row.previous_value) : '-'}</span> },
                  { key: 'after', header: 'New value', render: (row) => <span className="wrap mono">{row.new_value ? JSON.stringify(row.new_value) : '-'}</span> },
                  { key: 'ip', header: 'IP', render: (row) => row.ip_address || '-' },
                ]} />
              <div className="btn-row">
                <button type="button" className="btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
                <span className="muted">Page {page} of {Math.max(1, query.data.pages)}</span>
                <button type="button" className="btn" disabled={page >= query.data.pages} onClick={() => setPage(page + 1)}>Next</button>
              </div>
            </>
          )}
      </Panel>
    </>
  );
}
