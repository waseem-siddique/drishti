'use client';
import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, formatNumber } from '@/lib/api';
import { DataTable, ErrorState, Panel, Skeleton, TransparencyNote } from '@/components/ui';

type Rule = {
  rule_id: string; name: string; category: string; severity: string; weight: number;
  is_active: boolean; version: string; parameters: Record<string, number>; description?: string | null;
  required_fields: string[];
};

export default function RulesPage() {
  const client = useQueryClient();
  const [feedback, setFeedback] = React.useState<string | null>(null);
  const query = useQuery({
    queryKey: ['rules'],
    queryFn: () => api.get<{ rules: Rule[]; weights: Record<string, number>; weight_version?: string | null; ontology_version: string; engine_version: string }>('/risk/rules'),
  });
  const update = useMutation({
    mutationFn: (payload: { rule_id: string; body: Record<string, unknown> }) => api.patch('/admin/rules/' + payload.rule_id, payload.body),
    onSuccess: () => { setFeedback('Rule updated. A new rule version was recorded.'); client.invalidateQueries({ queryKey: ['rules'] }); },
    onError: (error) => setFeedback(error instanceof Error ? error.message : 'Only an administrator can change rules.'),
  });

  if (query.isLoading) return <Skeleton rows={8} />;
  if (query.error) return <ErrorState error={query.error} retry={() => query.refetch()} />;
  const data = query.data!;

  return (
    <>
      <h1>Rules and weights</h1>
      <p className="muted">
        Engine {data.engine_version} - ontology {data.ontology_version} - weight set {data.weight_version || '-'}.
        Every change is versioned and audited, so any past score can be reproduced.
      </p>
      {feedback ? <p className="notice" role="status">{feedback}</p> : null}
      <Panel title="Signal ontology" description="Weights and thresholds are configuration, not code.">
        <DataTable caption="Risk rules" rows={data.rules} rowKey={(row) => row.rule_id}
          columns={[
            { key: 'rule', header: 'Rule', render: (row) => (
              <div className="wrap">
                <span className="mono">{row.rule_id}</span> - {row.name}
                <p className="muted">{row.description}</p>
                <p className="muted">Needs: {row.required_fields.join(', ')}</p>
              </div>
            ) },
            { key: 'category', header: 'Family', render: (row) => row.category },
            { key: 'severity', header: 'Severity', render: (row) => row.severity },
            { key: 'version', header: 'Version', render: (row) => <span className="mono">{row.version}</span> },
            { key: 'weight', header: 'Weight', numeric: true, render: (row) => (
              <input type="number" step="0.05" min="0" max="2" defaultValue={row.weight} style={{ width: '5rem' }}
                onBlur={(event) => {
                  const weight = Number(event.target.value);
                  if (weight !== row.weight) update.mutate({ rule_id: row.rule_id, body: { weight } });
                }} />
            ) },
            { key: 'params', header: 'Thresholds', render: (row) => (
              <span className="wrap mono">{Object.entries(row.parameters).map(([key, value]) => key + '=' + formatNumber(value, 2)).join(', ')}</span>
            ) },
            { key: 'active', header: 'Active', render: (row) => (
              <input type="checkbox" checked={row.is_active} aria-label={'Enable ' + row.rule_id}
                onChange={(event) => update.mutate({ rule_id: row.rule_id, body: { is_active: event.target.checked } })} />
            ) },
          ]} />
      </Panel>
      <Panel title="Family weights" description="Applied by the risk composer after per-family capping.">
        {Object.entries(data.weights || {}).map(([family, weight]) => (
          <div key={family} className="row row--between"><span>{family}</span><span className="mono">{formatNumber(weight, 2)}</span></div>
        ))}
      </Panel>
      <TransparencyNote />
    </>
  );
}
