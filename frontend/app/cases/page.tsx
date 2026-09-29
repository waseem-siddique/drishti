'use client';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { api, formatDate, formatNumber } from '@/lib/api';
import { CaseStatusBadge, DataTable, EmptyState, ErrorState, Panel, PriorityBadge, Skeleton } from '@/components/ui';
import { useUiStore } from '@/state/uiStore';

type CaseRow = {
  case_ref: string; work_ref: string; status: string; status_label: string; priority?: string | null;
  priority_label?: string | null; risk_score?: number | null; assigned_to?: string | null;
  due_date?: string | null; outcome?: string | null; updated_at?: string | null;
};

const STATUSES = ['OPEN', 'ASSIGNED', 'UNDER_REVIEW', 'FIELD_VERIFICATION', 'ESCALATED', 'RESOLVED', 'CLOSED'];

export default function CasesPage() {
  const { caseStatusFilter, setCaseStatusFilter } = useUiStore();
  const params = new URLSearchParams();
  if (caseStatusFilter) params.set('case_status', caseStatusFilter);
  const query = useQuery({
    queryKey: ['cases', params.toString()],
    queryFn: () => api.get<{ items: CaseRow[] }>('/cases' + (params.toString() ? '?' + params.toString() : '')),
  });

  return (
    <>
      <h1>Verification cases</h1>
      <Panel title="Case queue" description="A case is a unit of human attention, not an accusation."
        actions={
          <label className="field">Status
            <select value={caseStatusFilter} onChange={(event) => setCaseStatusFilter(event.target.value)}>
              <option value="">All</option>
              {STATUSES.map((status) => <option key={status} value={status}>{status.replace(/_/g, ' ')}</option>)}
            </select>
          </label>
        }>
        {query.isLoading ? <Skeleton rows={6} /> : query.error ? <ErrorState error={query.error} retry={() => query.refetch()} />
          : !query.data?.items.length ? <EmptyState title="No cases yet" body="Open a case from a work dossier to start a verification trail." />
          : <DataTable caption="Verification cases" rows={query.data.items} rowKey={(row) => row.case_ref}
              columns={[
                { key: 'case_ref', header: 'Case', render: (row) => <Link className="mono nowrap" href={'/cases/' + row.case_ref}>{row.case_ref}</Link> },
                { key: 'work', header: 'Work', render: (row) => <Link className="mono" href={'/works/' + row.work_ref}>{row.work_ref}</Link> },
                { key: 'priority', header: 'Priority', render: (row) => <PriorityBadge priority={row.priority} label={row.priority_label} /> },
                { key: 'risk', header: 'Risk', numeric: true, render: (row) => formatNumber(row.risk_score, 1) },
                { key: 'status', header: 'Status', render: (row) => <CaseStatusBadge status={row.status} label={row.status_label} /> },
                { key: 'assigned', header: 'Assigned to', render: (row) => row.assigned_to || 'Unassigned' },
                { key: 'due', header: 'Due', render: (row) => formatDate(row.due_date) },
                { key: 'outcome', header: 'Outcome', render: (row) => row.outcome ? row.outcome.replace(/_/g, ' ') : 'Pending' },
              ]} />}
      </Panel>
    </>
  );
}
