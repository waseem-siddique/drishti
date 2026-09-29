'use client';
import Link from 'next/link';
import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, formatCurrency, formatDate, formatDateTime, formatNumber } from '@/lib/api';
import { CaseStatusBadge, EmptyState, ErrorState, FactorBar, Panel, PriorityBadge, RiskBadge, Skeleton, Timeline, TransparencyNote } from '@/components/ui';
import { useUiStore } from '@/state/uiStore';

type Workspace = {
  queue: Array<{ case_ref: string; work_ref: string; status: string; status_label: string; priority?: string | null; priority_label?: string | null; risk_score?: number | null; due_date?: string | null }>;
  selected: {
    case: { case_ref: string; work_ref: string; status: string; status_label: string; allowed_transitions: string[]; priority?: string | null; priority_label?: string | null; risk_score?: number | null; checklist: Array<{ id: string; label: string; done: boolean }>; calibration_note: string };
    timeline: Array<{ id: string; title: string; actor?: string | null; at: string; body?: string | null }>;
    dossier: { description?: string | null; district?: string | null; category?: string | null; sanction_amount?: number | null; expenditure?: number | null; progress_percent?: number | null; factors: Array<{ rule_id: string; name: string; contribution: number; statement?: string }>; recommended_actions: string[]; transparency_note: string } | null;
  } | null;
  outcomes: string[];
};

export default function VerificationWorkspacePage() {
  const { selectedCaseRef, setSelectedCaseRef, drafts, setDraft, clearDraft } = useUiStore();
  const client = useQueryClient();
  const [feedback, setFeedback] = React.useState<string | null>(null);
  const [outcome, setOutcome] = React.useState('');

  const query = useQuery({
    queryKey: ['workspace', selectedCaseRef],
    queryFn: () => api.get<Workspace>('/verification/workspace' + (selectedCaseRef ? '?case_ref=' + encodeURIComponent(selectedCaseRef) : '')),
  });
  const refresh = () => client.invalidateQueries({ queryKey: ['workspace'] });
  const fail = (error: unknown) => setFeedback(error instanceof Error ? error.message : 'That action could not be completed.');
  const active = query.data?.selected?.case;
  const noteKey = 'workspace-note-' + (active?.case_ref || 'none');

  const changeStatus = useMutation({ mutationFn: (status: string) => api.patch('/cases/' + active!.case_ref + '/status', { status }), onSuccess: refresh, onError: fail });
  const addNote = useMutation({ mutationFn: (body: string) => api.post('/cases/' + active!.case_ref + '/notes', { body }), onSuccess: () => { clearDraft(noteKey); refresh(); }, onError: fail });
  const recordOutcome = useMutation({ mutationFn: (value: string) => api.post('/cases/' + active!.case_ref + '/outcome', { outcome: value }), onSuccess: refresh, onError: fail });

  if (query.isLoading) return <Skeleton rows={10} />;
  if (query.error) return <ErrorState error={query.error} retry={() => query.refetch()} />;
  const data = query.data!;

  return (
    <>
      <h1>Verification workspace</h1>
      {feedback ? <p className="notice notice--warn" role="alert">{feedback}</p> : null}
      <div className="workspace">
        <Panel title={'Queue (' + data.queue.length + ')'} description="Highest verification priority first.">
          {data.queue.length === 0 ? <EmptyState title="Nothing is waiting" body="Open a case from a work dossier." /> : (
            <ul className="stack" style={{ listStyle: 'none', padding: 0 }}>
              {data.queue.map((item) => (
                <li key={item.case_ref}>
                  <button type="button" className="btn" style={{ width: '100%', textAlign: 'left' }} onClick={() => setSelectedCaseRef(item.case_ref)}>
                    <span className="row row--between">
                      <span className="mono">{item.case_ref}</span>
                      <PriorityBadge priority={item.priority} label={item.priority_label} />
                    </span>
                    <span className="muted">{item.work_ref} - risk {formatNumber(item.risk_score, 1)} - due {formatDate(item.due_date)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {active && data.selected ? (
          <>
            <Panel title={'Evidence review - ' + active.case_ref}
              actions={<Link className="btn" href={'/cases/' + active.case_ref}>Full case</Link>}>
              <div className="row row--between">
                <RiskBadge band={(active.risk_score ?? 0) >= 70 ? 'HIGH' : (active.risk_score ?? 0) >= 40 ? 'MEDIUM' : 'LOW'} score={active.risk_score ?? null} />
                <CaseStatusBadge status={active.status} label={active.status_label} />
              </div>
              <h3>{data.selected.dossier?.description}</h3>
              <p className="muted mono">
                {data.selected.dossier?.district} - sanctioned {formatCurrency(data.selected.dossier?.sanction_amount)} - spent {formatCurrency(data.selected.dossier?.expenditure)} - progress {formatNumber(data.selected.dossier?.progress_percent, 1)}%
              </p>
              {(data.selected.dossier?.factors || []).map((factor) => (
                <FactorBar key={factor.rule_id} label={factor.rule_id + ' - ' + factor.name} contribution={factor.contribution} detail={factor.statement} />
              ))}
            </Panel>

            <Panel title="Decision" description={active.calibration_note}>
              <h4>Checklist</h4>
              <ul style={{ paddingLeft: '1.1rem' }}>
                {active.checklist.map((item) => <li key={item.id}>{item.done ? '[x] ' : '[ ] '}{item.label}</li>)}
              </ul>
              <div className="btn-row">
                {active.allowed_transitions.map((status) => (
                  <button key={status} type="button" className="btn" onClick={() => changeStatus.mutate(status)}>{status.replace(/_/g, ' ').toLowerCase()}</button>
                ))}
              </div>
              <label className="field">Outcome
                <select value={outcome} onChange={(event) => setOutcome(event.target.value)}>
                  <option value="">Select an outcome</option>
                  {data.outcomes.map((value) => <option key={value} value={value}>{value.replace(/_/g, ' ')}</option>)}
                </select>
              </label>
              <label className="field">Note
                <textarea value={drafts[noteKey] || ''} onChange={(event) => setDraft(noteKey, event.target.value)} />
              </label>
              <div className="btn-row">
                <button type="button" className="btn" disabled={!drafts[noteKey]} onClick={() => addNote.mutate(drafts[noteKey])}>Save note</button>
                <button type="button" className="btn btn--primary" disabled={!outcome} onClick={() => recordOutcome.mutate(outcome)}>Record outcome</button>
              </div>
            </Panel>
          </>
        ) : <Panel title="Evidence review"><EmptyState title="Select a case from the queue" /></Panel>}
      </div>

      {data.selected ? (
        <Panel title="Activity">
          <Timeline items={data.selected.timeline.map((item) => ({ id: item.id, title: item.title, meta: (item.actor ? item.actor + ' - ' : '') + formatDateTime(item.at), body: item.body || undefined }))} />
        </Panel>
      ) : null}
      <TransparencyNote note={data.selected?.dossier?.transparency_note} />
    </>
  );
}
