'use client';
import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, formatDateTime, formatNumber } from '@/lib/api';
import { DataTable, EmptyState, ErrorState, Panel, Skeleton } from '@/components/ui';

type Job = { id: number; filename: string; status: string; records_received?: number | null; records_accepted?: number | null; records_rejected?: number | null; processing_seconds?: number | null; is_prototype?: boolean; error?: string | null; created_at: string };
type JobDetail = {
  id: number; filename: string; status: string; columns?: string[] | null; warnings?: string[] | null;
  rejected_records?: Array<{ row: number; reason: string }> | null;
  column_profiles?: Record<string, Record<string, unknown>> | null;
  mapping: Array<{ canonical_field: string; source_column?: string | null; status: string; note?: string | null }>;
};

export default function IngestionPage() {
  const client = useQueryClient();
  const [selected, setSelected] = React.useState<number | null>(null);
  const [feedback, setFeedback] = React.useState<string | null>(null);

  const jobs = useQuery({ queryKey: ['jobs'], queryFn: () => api.get<{ jobs: Job[] }>('/ingestion/jobs') });
  const detail = useQuery({ queryKey: ['job', selected], queryFn: () => api.get<JobDetail>('/ingestion/jobs/' + selected), enabled: selected !== null });

  const upload = useMutation({
    mutationFn: (file: File) => { const form = new FormData(); form.append('file', file); return api.upload<{ dataset_id: number }>('/ingestion/upload', form); },
    onSuccess: (result) => { setFeedback('Upload processed and analysed.'); setSelected(result.dataset_id); client.invalidateQueries(); },
    onError: (error) => setFeedback(error instanceof Error ? error.message : 'Upload failed.'),
  });
  const analyse = useMutation({
    mutationFn: () => api.post<{ works_analysed: number }>('/risk/analyze'),
    onSuccess: (result) => { setFeedback('Re-analysed ' + result.works_analysed + ' works.'); client.invalidateQueries(); },
    onError: (error) => setFeedback(error instanceof Error ? error.message : 'Analysis failed.'),
  });

  return (
    <>
      <h1>Ingestion</h1>
      <Panel title="Upload a dataset" description="CSV, Excel or JSON. Columns are detected and mapped; nothing is silently discarded."
        actions={<button type="button" className="btn" onClick={() => analyse.mutate()} disabled={analyse.isPending}>Re-run risk analysis</button>}>
        <label className="btn btn--primary" style={{ display: 'inline-block' }}>
          {upload.isPending ? 'Processing' : 'Choose file'}
          <input type="file" accept=".csv,.xlsx,.xls,.json" style={{ display: 'none' }}
            onChange={(event) => { const file = event.target.files?.[0]; if (file) upload.mutate(file); }} />
        </label>
        {feedback ? <p className="notice" role="status">{feedback}</p> : null}
      </Panel>

      <Panel title="Ingestion jobs">
        {jobs.isLoading ? <Skeleton /> : jobs.error ? <ErrorState error={jobs.error} /> : !jobs.data?.jobs.length ? <EmptyState title="No uploads yet" /> : (
          <DataTable caption="Ingestion jobs" rows={jobs.data.jobs} rowKey={(row) => row.id}
            columns={[
              { key: 'file', header: 'File', render: (row) => (
                <button type="button" className="sort-button" onClick={() => setSelected(row.id)}>
                  {row.filename}{row.is_prototype ? ' (prototype)' : ''}
                </button>
              ) },
              { key: 'status', header: 'Status', render: (row) => row.status },
              { key: 'received', header: 'Received', numeric: true, render: (row) => formatNumber(row.records_received) },
              { key: 'accepted', header: 'Accepted', numeric: true, render: (row) => formatNumber(row.records_accepted) },
              { key: 'rejected', header: 'Rejected', numeric: true, render: (row) => formatNumber(row.records_rejected) },
              { key: 'seconds', header: 'Seconds', numeric: true, render: (row) => formatNumber(row.processing_seconds, 2) },
              { key: 'created', header: 'Uploaded', render: (row) => formatDateTime(row.created_at) },
              { key: 'error', header: 'Error', render: (row) => row.error || '-' },
            ]} />
        )}
      </Panel>

      {selected !== null ? (
        <Panel title="Job detail" description="Source to canonical mapping and rejection report.">
          {detail.isLoading ? <Skeleton /> : detail.error ? <ErrorState error={detail.error} /> : detail.data ? (
            <div className="stack">
              <p className="muted">Columns found: {(detail.data.columns || []).join(', ') || 'None'}</p>
              <DataTable caption="Field mapping" rows={detail.data.mapping} rowKey={(row) => row.canonical_field}
                columns={[
                  { key: 'field', header: 'Canonical field', render: (row) => <span className="mono">{row.canonical_field}</span> },
                  { key: 'source', header: 'Source column', render: (row) => row.source_column || '-' },
                  { key: 'status', header: 'Status', render: (row) => row.status },
                  { key: 'note', header: 'Note', render: (row) => <span className="wrap">{row.note || '-'}</span> },
                ]} />
              <h3>Warnings</h3>
              <ul>{(detail.data.warnings || []).map((item) => <li key={item}>{item}</li>)}</ul>
              <h3>Rejected records</h3>
              {(detail.data.rejected_records || []).length === 0 ? <p className="muted">No record was rejected.</p> : (
                <ul>{(detail.data.rejected_records || []).map((item, index) => <li key={index}>Row {item.row}: {item.reason}</li>)}</ul>
              )}
            </div>
          ) : null}
        </Panel>
      ) : null}
    </>
  );
}
