'use client';
import { useQuery } from '@tanstack/react-query';
import { api, formatCurrency, formatNumber } from '@/lib/api';
import { DataTable, EmptyState, ErrorState, Kpi, Panel, Skeleton, TransparencyNote } from '@/components/ui';

type Category = { category: string; works: number; high_risk: number; sanctioned: number | null; expenditure: number | null; avg_risk: number | null };
type Geo = { state: string; district: string; works: number; high_risk: number; sanctioned: number | null; avg_risk: number | null; has_coordinates: boolean };
type Outcomes = {
  cases_total: number; cases_with_outcome: number; alert_precision: number | null;
  false_positive_rate: number | null; closure_rate: number | null; avg_review_hours: number | null;
  backlog: number; early_warning_lead_days: number | null;
  signal_usefulness: Array<{ rule_id: string; confirmed_useful: number; not_useful: number; pending: number }>;
  evidence_sufficiency: number | null; calibration_note: string;
};
type CaseLoad = { by_status: Array<{ status: string; count: number }>; by_assignee: Array<{ assignee: string; open: number; resolved: number }> };

export default function AnalyticsPage() {
  const categories = useQuery({ queryKey: ['an-cat'], queryFn: () => api.get<{ categories: Category[] }>('/analytics/categories') });
  const geography = useQuery({ queryKey: ['an-geo'], queryFn: () => api.get<{ rows: Geo[]; map_note?: string | null }>('/analytics/geography') });
  const outcomes = useQuery({ queryKey: ['an-out'], queryFn: () => api.get<Outcomes>('/analytics/outcomes') });
  const caseLoad = useQuery({ queryKey: ['an-load'], queryFn: () => api.get<CaseLoad>('/analytics/case-load') });

  return (
    <>
      <h1>Analytics</h1>
      <Panel title="Verification outcomes" description="Measured from recorded case outcomes only.">
        {outcomes.isLoading ? <Skeleton rows={4} /> : outcomes.error ? <ErrorState error={outcomes.error} /> : outcomes.data ? (
          <>
            <div className="kpi-grid">
              <Kpi label="Cases with an outcome" value={formatNumber(outcomes.data.cases_with_outcome)} meta={'of ' + formatNumber(outcomes.data.cases_total) + ' cases'} />
              <Kpi label="Alert precision" value={outcomes.data.alert_precision === null ? 'Not enough outcomes' : outcomes.data.alert_precision + '%'} />
              <Kpi label="False positive rate" value={outcomes.data.false_positive_rate === null ? 'Not enough outcomes' : outcomes.data.false_positive_rate + '%'} tone="medium" />
              <Kpi label="Closure rate" value={outcomes.data.closure_rate === null ? 'Not available' : outcomes.data.closure_rate + '%'} />
              <Kpi label="Average review time" value={outcomes.data.avg_review_hours === null ? 'Not available' : formatNumber(outcomes.data.avg_review_hours, 1) + ' h'} />
              <Kpi label="Open backlog" value={formatNumber(outcomes.data.backlog)} tone="high" />
            </div>
            <h3>Signal usefulness</h3>
            {outcomes.data.signal_usefulness.length === 0 ? <EmptyState title="No signal has been judged yet" body="Record case outcomes to calibrate the rules." /> : (
              <DataTable caption="Signal usefulness by rule" rows={outcomes.data.signal_usefulness} rowKey={(row) => row.rule_id}
                columns={[
                  { key: 'rule', header: 'Rule', render: (row) => <span className="mono">{row.rule_id}</span> },
                  { key: 'useful', header: 'Confirmed useful', numeric: true, render: (row) => formatNumber(row.confirmed_useful) },
                  { key: 'not', header: 'Not useful', numeric: true, render: (row) => formatNumber(row.not_useful) },
                  { key: 'pending', header: 'Pending', numeric: true, render: (row) => formatNumber(row.pending) },
                ]} />
            )}
            <TransparencyNote note={outcomes.data.calibration_note} />
          </>
        ) : null}
      </Panel>

      <Panel title="Category concentration">
        {categories.isLoading ? <Skeleton /> : categories.error ? <ErrorState error={categories.error} /> : (
          <DataTable caption="Risk by work category" rows={categories.data?.categories || []} rowKey={(row) => row.category}
            columns={[
              { key: 'category', header: 'Category', render: (row) => row.category },
              { key: 'works', header: 'Works', numeric: true, render: (row) => formatNumber(row.works) },
              { key: 'high', header: 'High risk', numeric: true, render: (row) => formatNumber(row.high_risk) },
              { key: 'avg', header: 'Average risk', numeric: true, render: (row) => formatNumber(row.avg_risk, 1) },
              { key: 'sanctioned', header: 'Sanctioned', numeric: true, render: (row) => formatCurrency(row.sanctioned) },
              { key: 'spent', header: 'Spent', numeric: true, render: (row) => formatCurrency(row.expenditure) },
            ]} />
        )}
      </Panel>

      <Panel title="Geography" description="Districts ranked by high-risk concentration.">
        {geography.isLoading ? <Skeleton /> : geography.error ? <ErrorState error={geography.error} /> : (
          <>
            {geography.data?.map_note ? <p className="notice notice--warn">{geography.data.map_note}</p> : null}
            <DataTable caption="Risk by district" rows={geography.data?.rows || []} rowKey={(row) => row.state + '-' + row.district}
              columns={[
                { key: 'state', header: 'State', render: (row) => row.state },
                { key: 'district', header: 'District', render: (row) => row.district },
                { key: 'works', header: 'Works', numeric: true, render: (row) => formatNumber(row.works) },
                { key: 'high', header: 'High risk', numeric: true, render: (row) => formatNumber(row.high_risk) },
                { key: 'avg', header: 'Average risk', numeric: true, render: (row) => formatNumber(row.avg_risk, 1) },
                { key: 'sanctioned', header: 'Sanctioned', numeric: true, render: (row) => formatCurrency(row.sanctioned) },
              ]} />
          </>
        )}
      </Panel>

      <Panel title="Case load">
        {caseLoad.isLoading ? <Skeleton /> : caseLoad.error ? <ErrorState error={caseLoad.error} /> : (
          <div className="split">
            <div className="stack">
              <h3>By status</h3>
              {(caseLoad.data?.by_status || []).map((row) => (
                <div key={row.status} className="row row--between"><span>{row.status.replace(/_/g, ' ')}</span><strong className="mono">{row.count}</strong></div>
              ))}
            </div>
            <div className="stack">
              <h3>By reviewer</h3>
              {(caseLoad.data?.by_assignee || []).length === 0 ? <span className="muted">Nothing assigned yet</span> : (caseLoad.data?.by_assignee || []).map((row) => (
                <div key={row.assignee} className="row row--between"><span>{row.assignee}</span><span className="muted mono">{row.open} open / {row.resolved} resolved</span></div>
              ))}
            </div>
          </div>
        )}
      </Panel>
    </>
  );
}
