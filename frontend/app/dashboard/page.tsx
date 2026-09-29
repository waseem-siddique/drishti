'use client';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { api, formatCurrency, formatNumber } from '@/lib/api';
import { ErrorState, Kpi, Panel, PriorityBadge, RiskBadge, Skeleton, TransparencyNote, DataTable, EmptyState } from '@/components/ui';

type Summary = {
  works_total: number; works_scored: number; high_risk: number; p1_count: number;
  open_cases: number; sanctioned_total: number | null; expenditure_total: number | null;
  dataset_quality: { score: number | null; note: string } | null;
  prototype_label?: string | null; transparency_note: string;
  queue: Array<{ work_id: string; description?: string | null; district?: string | null; risk_score: number; risk_band: string; confidence_score: number; priority: string; priority_label: string; sanction_amount?: number | null; top_reason?: string | null }>;
};

export default function DashboardPage() {
  const summary = useQuery({ queryKey: ['summary'], queryFn: () => api.get<Summary>('/dashboard/summary') });
  const distribution = useQuery({ queryKey: ['distribution'], queryFn: () => api.get<{ bands: Array<{ band: string; count: number }>; categories: Array<{ category: string; count: number; high: number }> }>('/dashboard/risk-distribution') });

  if (summary.isLoading) return <Skeleton rows={8} />;
  if (summary.error) return <ErrorState error={summary.error} retry={() => summary.refetch()} />;
  const data = summary.data!;

  return (
    <>
      <div className="row row--between">
        <h1>Command centre</h1>
        <span className="muted">{formatNumber(data.works_scored)} of {formatNumber(data.works_total)} works scored by the current engine version</span>
      </div>
      {data.prototype_label ? <p className="notice notice--prototype">Dataset: {data.prototype_label}</p> : null}
      <div className="kpi-grid">
        <Kpi label="Works under oversight" value={formatNumber(data.works_total)} meta={'Sanctioned ' + formatCurrency(data.sanctioned_total)} />
        <Kpi label="High risk works" value={formatNumber(data.high_risk)} tone="high" meta="Risk band HIGH (>= 70)" />
        <Kpi label="P1 - verify first" value={formatNumber(data.p1_count)} tone="high" meta="Priority index >= 68" />
        <Kpi label="Open verification cases" value={formatNumber(data.open_cases)} tone="medium" meta="Not resolved or closed" />
        <Kpi label="Reported expenditure" value={formatCurrency(data.expenditure_total)} meta="Sum of expenditure field" />
        <Kpi label="Dataset quality" value={data.dataset_quality?.score ?? 'Not available'} meta="Completeness, validity, consistency, timeliness" />
      </div>
      <div className="split">
        <Panel title="Verification queue" description="Ordered by verification priority index, not by risk alone."
          actions={<Link className="btn" href="/works">Open works explorer</Link>}>
            {data.queue.length === 0 ? (
              <EmptyState title="Nothing is queued" body="Run an analysis from the ingestion screen once a dataset has been uploaded." />
            ) : (
              <DataTable
                caption="Works needing verification first"
                rows={data.queue}
                rowKey={(row) => row.work_id}
                columns={[
                  { key: 'priority', header: 'Priority', render: (row) => <PriorityBadge priority={row.priority} label={row.priority_label} /> },
                  { key: 'work', header: 'Work', render: (row) => (
                    <div className="wrap">
                      <Link href={'/works/' + row.work_id} className="mono">{row.work_id}</Link>
                      <p className="muted">{row.description || ''}</p>
                      {row.top_reason ? <p className="muted">Why: {row.top_reason}</p> : null}
                    </div>
                  ) },
                  { key: 'district', header: 'District', render: (row) => row.district || '-' },
                  { key: 'risk', header: 'Risk', render: (row) => <RiskBadge band={row.risk_band} score={row.risk_score} /> },
                  { key: 'confidence', header: 'Confidence', numeric: true, render: (row) => formatNumber(row.confidence_score, 1) },
                  { key: 'amount', header: 'Sanctioned', numeric: true, render: (row) => formatCurrency(row.sanction_amount) },
                ]}
              />
            )}
        </Panel>
        <Panel title="Risk distribution" description="Counts come from stored risk results.">
          {distribution.isLoading ? <Skeleton /> : distribution.error ? <ErrorState error={distribution.error} /> : (
            <div className="stack">
              {(distribution.data?.bands || []).map((band) => (
                <div key={band.band} className="row row--between">
                  <RiskBadge band={band.band} score={null} />
                  <strong className="mono">{formatNumber(band.count)}</strong>
                </div>
              ))}
              <h3>By category</h3>
              {(distribution.data?.categories || []).slice(0, 8).map((row) => (
                <div key={row.category} className="row row--between">
                  <span>{row.category}</span>
                  <span className="muted mono">{row.high} high / {row.count}</span>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>
      <TransparencyNote note={data.transparency_note} />
    </>
  );
}
