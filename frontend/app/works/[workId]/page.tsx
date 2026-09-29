'use client';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, formatCurrency, formatDate, formatNumber, NO_DATA } from '@/lib/api';
import { ConfidenceMeter, ErrorState, FactorBar, Panel, PriorityBadge, RiskBadge, Skeleton, Timeline, TransparencyNote, Unavailable } from '@/components/ui';

type Signal = {
  rule_id: string; name: string; category: string; severity: string; strength: number;
  contribution: number; statement: string; method: string; evidence: Array<{ field?: string; value?: string; note?: string }>;
  recommended_actions: string[]; false_positive_notes: string[]; peer?: Record<string, unknown> | null;
};
type Dossier = {
  work_id: string; description?: string | null; state?: string | null; district?: string | null;
  constituency?: string | null; category?: string | null; agency?: string | null; status?: string | null;
  sanction_amount?: number | null; expenditure?: number | null; progress_percent?: number | null;
  sanction_date?: string | null; expected_completion?: string | null; actual_completion?: string | null;
  risk: { risk_score: number | null; risk_band: string | null; confidence_score: number | null; confidence_label?: string | null; priority?: string | null; priority_label?: string | null; priority_index?: number | null; engine_version?: string; weight_version?: string; computed_at?: string | null } | null;
  factors: Array<{ rule_id: string; name: string; contribution: number; statement?: string }>;
  signals: Signal[];
  peer_benchmark: Array<{ metric: string; value: number | null; peer_median: number | null; percentile: number | null; peer_count: number; group_label: string }>;
  data_quality: { score: number | null; dimensions?: Record<string, number>; missing_fields?: string[]; note: string } | null;
  field_availability: Record<string, { status: string; note?: string }>;
  gated_rules: Array<{ rule_id: string; name: string; missing_fields: string[] }>;
  case_ref?: string | null; recommended_actions: string[];
  evidence: Array<{ id: number; original_filename: string; checksum_sha256: string; uploaded_at: string; authenticity_note: string }>;
  transparency_note: string;
};

export default function WorkDossierPage() {
  const params = useParams<{ workId: string }>();
  const router = useRouter();
  const client = useQueryClient();
  const workId = decodeURIComponent(String(params.workId));
  const [message, setMessage] = React.useState<string | null>(null);

  const query = useQuery({ queryKey: ['work', workId], queryFn: () => api.get<Dossier>('/works/' + encodeURIComponent(workId)) });
  const explain = useMutation({ mutationFn: () => api.post<{ narrative: string; disclaimer: string; model?: Record<string, unknown>; warning?: string }>('/risk/explain', { work_ref: workId }) });
  const openCase = useMutation({
    mutationFn: () => api.post<{ case_ref: string }>('/cases', { work_ref: workId }),
    onSuccess: (result) => { client.invalidateQueries({ queryKey: ['work', workId] }); router.push('/cases/' + result.case_ref); },
    onError: (error) => setMessage(error instanceof Error ? error.message : 'Could not open a case.'),
  });

  if (query.isLoading) return <Skeleton rows={10} />;
  if (query.error) return <ErrorState error={query.error} retry={() => query.refetch()} />;
  const work = query.data!;
  const risk = work.risk;

  return (
    <>
      <div className="row row--between">
        <div className="stack">
          <div className="row">
            {risk?.priority ? <PriorityBadge priority={risk.priority} label={risk.priority_label} /> : null}
            <RiskBadge band={risk?.risk_band} score={risk?.risk_score ?? null} />
            <span className="mono">{work.work_id}</span>
          </div>
          <h1>{work.description || 'Work record'}</h1>
          <p className="muted">
            {[work.district, work.state, work.category, work.agency].filter(Boolean).join(' - ') || NO_DATA}
          </p>
        </div>
        <div className="btn-row">
          {work.case_ref
            ? <Link className="btn" href={'/cases/' + work.case_ref}>Open case {work.case_ref}</Link>
            : <button type="button" className="btn btn--primary" onClick={() => openCase.mutate()} disabled={openCase.isPending}>Open verification case</button>}
          <button type="button" className="btn" onClick={() => explain.mutate()} disabled={explain.isPending}>Explain in plain language</button>
        </div>
      </div>
      {message ? <p className="notice notice--warn" role="alert">{message}</p> : null}

      <div className="split">
        <Panel title="Risk factor breakdown" description="Contributions are computed by the engine, not by a language model.">
          {work.factors.length === 0 ? <p className="muted">No rule fired on this record.</p> : work.factors.map((factor) => (
            <FactorBar key={factor.rule_id} label={factor.rule_id + ' - ' + factor.name} contribution={factor.contribution} detail={factor.statement} />
          ))}
          <div className="stack" style={{ marginTop: '0.75rem' }}>
            <ConfidenceMeter score={risk?.confidence_score ?? null} label={risk?.confidence_label || undefined} />
            <p className="muted">
              Engine {risk?.engine_version || '-'} - weights {risk?.weight_version || '-'} - priority index {formatNumber(risk?.priority_index ?? null, 2)} - computed {formatDate(risk?.computed_at)}
            </p>
          </div>
        </Panel>
        <Panel title="Record">
          <dl className="stack">
            {[['Sanctioned amount', formatCurrency(work.sanction_amount)],
              ['Reported expenditure', formatCurrency(work.expenditure)],
              ['Physical progress', work.progress_percent === null || work.progress_percent === undefined ? NO_DATA : formatNumber(work.progress_percent, 1) + '%'],
              ['Sanctioned on', formatDate(work.sanction_date)],
              ['Expected completion', formatDate(work.expected_completion)],
              ['Actual completion', formatDate(work.actual_completion)],
              ['Reported status', work.status || NO_DATA],
              ['Constituency', work.constituency || NO_DATA]].map(([label, value]) => (
              <div key={String(label)} className="row row--between">
                <dt className="muted">{label}</dt>
                <dd className="mono" style={{ margin: 0 }}>{value}</dd>
              </div>
            ))}
          </dl>
        </Panel>
      </div>

      <Panel title="Why this was flagged" description="Signal, source field, detection method, contribution, evidence and recommended action.">
        {work.signals.length === 0 ? <p className="muted">Nothing was flagged on this record.</p> : (
          <div className="stack">
            {work.signals.map((signal) => (
              <article key={signal.rule_id} className="panel">
                <header className="panel-header">
                  <div>
                    <h3>{signal.rule_id} - {signal.name}</h3>
                    <p className="muted">{signal.category} - severity {signal.severity} - method {signal.method}</p>
                  </div>
                  <span className="mono">+{signal.contribution.toFixed(1)}</span>
                </header>
                <div className="panel-body stack">
                  <p>{signal.statement}</p>
                  <div>
                    <h4 className="muted">Evidence from the dataset</h4>
                    <ul>
                      {signal.evidence.map((item, index) => (
                        <li key={index}><span className="mono">{item.field || 'derived'}</span>: {item.value ?? NO_DATA}{item.note ? ' - ' + item.note : ''}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <h4 className="muted">Recommended next action</h4>
                    <ul>{signal.recommended_actions.map((action) => <li key={action}>{action}</li>)}</ul>
                  </div>
                  {signal.false_positive_notes.length ? (
                    <details>
                      <summary>Legitimate explanations to rule out first</summary>
                      <ul>{signal.false_positive_notes.map((note) => <li key={note}>{note}</li>)}</ul>
                    </details>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        )}
      </Panel>

      <div className="split">
        <Panel title="Peer benchmarking" description="Compared with similar works, not with the national average.">
          {work.peer_benchmark.length === 0 ? <Unavailable>Not enough peers in the current dataset</Unavailable> : work.peer_benchmark.map((row) => (
            <div key={row.metric} className="factor-row">
              <div className="row row--between"><strong>{row.metric}</strong><span className="muted">{row.group_label} ({row.peer_count} peers)</span></div>
              <p className="muted">This work {formatNumber(row.value, 0)} - peer median {formatNumber(row.peer_median, 0)} - percentile {formatNumber(row.percentile, 0)}</p>
            </div>
          ))}
        </Panel>
        <Panel title="Data quality and availability">
          <p className="muted">Record quality score: <strong>{work.data_quality?.score ?? 'Not available'}</strong></p>
          <p className="muted">{work.data_quality?.note}</p>
          <h4>Fields not present in this dataset</h4>
          <ul>
            {Object.entries(work.field_availability).filter(([, spec]) => spec.status !== 'AVAILABLE').map(([field, spec]) => (
              <li key={field}><span className="mono">{field}</span> - {spec.status}</li>
            ))}
          </ul>
          {work.gated_rules.length ? (
            <>
              <h4>Rules that could not be evaluated</h4>
              <ul>{work.gated_rules.map((rule) => <li key={rule.rule_id}>{rule.rule_id} - needs {rule.missing_fields.join(', ')}</li>)}</ul>
            </>
          ) : null}
        </Panel>
      </div>

      {explain.data ? (
        <Panel title="Plain language summary" description="Generated from the stored signals only.">
          <p>{explain.data.narrative}</p>
          {explain.data.warning ? <p className="notice notice--warn">{explain.data.warning}</p> : null}
          <p className="transparency-note">{explain.data.disclaimer}</p>
        </Panel>
      ) : null}

      <Panel title="Evidence on file">
        {work.evidence.length === 0 ? <p className="muted">No documents attached.</p> : (
          <Timeline items={work.evidence.map((item) => ({
            id: item.id,
            title: item.original_filename,
            meta: formatDate(item.uploaded_at),
            body: 'SHA-256 ' + item.checksum_sha256.slice(0, 16) + '... - ' + item.authenticity_note,
          }))} />
        )}
      </Panel>
      <TransparencyNote note={work.transparency_note} />
    </>
  );
}
