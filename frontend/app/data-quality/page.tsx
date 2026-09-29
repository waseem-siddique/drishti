'use client';
import { useQuery } from '@tanstack/react-query';
import { api, formatNumber } from '@/lib/api';
import { DataTable, EmptyState, ErrorState, Kpi, Panel, Skeleton, TransparencyNote, Unavailable } from '@/components/ui';

type Quality = {
  dataset: { score: number | null; dimensions: Record<string, number>; note: string; computed_at?: string | null } | null;
  worst_records: Array<{ work_id: string; score: number; missing_fields: string[] }>;
  field_availability: Record<string, { status: string; note?: string }>;
  missing_field_counts: Array<{ field: string; missing: number }>;
  prototype_label?: string | null;
};

export default function DataQualityPage() {
  const query = useQuery({ queryKey: ['quality'], queryFn: () => api.get<Quality>('/data-quality') });
  if (query.isLoading) return <Skeleton rows={8} />;
  if (query.error) return <ErrorState error={query.error} retry={() => query.refetch()} />;
  const data = query.data!;

  return (
    <>
      <h1>Data quality</h1>
      {data.prototype_label ? <p className="notice notice--prototype">Dataset: {data.prototype_label}</p> : null}
      {!data.dataset ? <EmptyState title="No dataset has been analysed yet" body="Upload a dataset from the ingestion screen." /> : (
        <>
          <div className="kpi-grid">
            <Kpi label="Dataset quality" value={data.dataset.score ?? 'Not available'} meta="0 to 100" />
            {Object.entries(data.dataset.dimensions || {}).map(([name, value]) => (
              <Kpi key={name} label={name} value={formatNumber(value, 1)} />
            ))}
          </div>
          <p className="notice notice--warn">{data.dataset.note}</p>
        </>
      )}

      <Panel title="Field availability" description="What the source file actually contains.">
        <DataTable caption="Canonical field availability" rows={Object.entries(data.field_availability).map(([field, spec]) => ({ field, ...spec }))}
          rowKey={(row) => row.field}
          columns={[
            { key: 'field', header: 'Canonical field', render: (row) => <span className="mono">{row.field}</span> },
            { key: 'status', header: 'Status', render: (row) => row.status },
            { key: 'note', header: 'Note', render: (row) => row.note ? <span className="wrap">{row.note}</span> : <Unavailable /> },
          ]} />
      </Panel>

      <div className="split">
        <Panel title="Most incomplete records">
          {data.worst_records.length === 0 ? <p className="muted">Every scored record has complete mandatory fields.</p> : (
            <DataTable caption="Records with the lowest quality score" rows={data.worst_records} rowKey={(row) => row.work_id}
              columns={[
                { key: 'work', header: 'Work', render: (row) => <span className="mono">{row.work_id}</span> },
                { key: 'score', header: 'Quality', numeric: true, render: (row) => formatNumber(row.score, 1) },
                { key: 'missing', header: 'Missing fields', render: (row) => <span className="wrap">{row.missing_fields.join(', ') || '-'}</span> },
              ]} />
          )}
        </Panel>
        <Panel title="Missing values by field">
          {data.missing_field_counts.map((row) => (
            <div key={row.field} className="row row--between"><span className="mono">{row.field}</span><strong className="mono">{formatNumber(row.missing)}</strong></div>
          ))}
        </Panel>
      </div>
      <TransparencyNote />
    </>
  );
}
