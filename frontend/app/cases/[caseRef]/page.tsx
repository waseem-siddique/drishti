'use client';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, formatCurrency, formatDate, formatDateTime, formatNumber } from '@/lib/api';
import { CaseStatusBadge, ConfidenceMeter, ErrorState, FactorBar, Panel, PriorityBadge, RiskBadge, Skeleton, Timeline, TransparencyNote } from '@/components/ui';
import { useUiStore } from '@/state/uiStore';

type CaseDetail = {
  case: {
    case_ref: string; work_ref: string; status: string; status_label: string; allowed_transitions: string[];
    priority?: string | null; priority_label?: string | null; risk_score?: number | null;
    confidence_score?: number | null; assigned_to?: string | null; assigned_to_id?: number | null;
    due_date?: string | null; outcome?: string | null; outcome_recorded_at?: string | null;
    checklist: Array<{ id: string; label: string; done: boolean }>; calibration_note: string;
  };
  timeline: Array<{ id: string; kind: string; title: string; actor?: string | null; at: string; body?: string | null }>;
  dossier: {
    description?: string | null; district?: string | null; category?: string | null; agency?: string | null;
    sanction_amount?: number | null; expenditure?: number | null; progress_percent?: number | null;
    factors: Array<{ rule_id: string; name: string; contribution: number; statement?: string }>;
    recommended_actions: string[]; transparency_note: string;
  } | null;
  evidence: Array<{ id: number; original_filename: string; checksum_sha256: string; uploaded_at: string; authenticity_note: string }>;
  outcomes: string[];
};

export default function CaseDetailPage() {
  const params = useParams<{ caseRef: string }>();
  const caseRef = decodeURIComponent(String(params.caseRef));
  const client = useQueryClient();
  const { drafts, setDraft, clearDraft } = useUiStore();
  const noteKey = 'case-note-' + caseRef;
  const [feedback, setFeedback] = React.useState<string | null>(null);
  const [outcome, setOutcome] = React.useState('');

  const query = useQuery({ queryKey: ['case', caseRef], queryFn: () => api.get<CaseDetail>('/cases/' + encodeURIComponent(caseRef)) });
  const refresh = () => client.invalidateQueries({ queryKey: ['case', caseRef] });
  const fail = (error: unknown) => setFeedback(error instanceof Error ? error.message : 'That action could not be completed.');

  const changeStatus = useMutation({ mutationFn: (status: string) => api.patch('/cases/' + caseRef + '/status', { status }), onSuccess: refresh, onError: fail });
  const addNote = useMutation({
    mutationFn: (body: string) => api.post('/cases/' + caseRef + '/notes', { body }),
    onSuccess: () => { clearDraft(noteKey); refresh(); }, onError: fail,
  });
  const recordOutcome = useMutation({ mutationFn: (value: string) => api.post('/cases/' + caseRef + '/outcome', { outcome: value }), onSuccess: refresh, onError: fail });
  const toggleChecklist = useMutation({
    mutationFn: (checklist: Array<{ id: string; label: string; done: boolean }>) => api.patch('/cases/' + caseRef + '/checklist', { checklist }),
    onSuccess: refresh, onError: fail,
  });
  const uploadEvidence = useMutation({
    mutationFn: (file: File) => { const form = new FormData(); form.append('file', file); return api.upload('/cases/' + caseRef + '/evidence', form); },
    onSuccess: refresh, onError: fail,
  });

  if (query.isLoading) return <Skeleton rows={10} />;
  if (query.error) return <ErrorState error={query.error} retry={() => query.refetch()} />;
  const detail = query.data!;
  const record = detail.case;

  return (
    <>
      <div className="row row--between">
        <div className="stack">
          <div className="row">
            <PriorityBadge priority={record.priority} label={record.priority_label} />
            <CaseStatusBadge status={record.status} label={record.status_label} />
            <span className="mono">{record.case_ref}</span>
          </div>
          <h1>{detail.dossier?.description || record.work_ref}</h1>
          <p className="muted">
            Work <Link className="mono" href={'/works/' + record.work_ref}>{record.work_ref}</Link>
            {' - '}{[detail.dossier?.district, detail.dossier?.category, detail.dossier?.agency].filter(Boolean).join(' - ')}
            {' - due '}{formatDate(record.due_date)}
          </p>
        </div>
        <div className="btn-row">
          {record.allowed_transitions.map((status) => (
            <button key={status} type="button" className="btn" onClick={() => changeStatus.mutate(status)} disabled={changeStatus.isPending}>
              Move to {status.replace(/_/g, ' ').toLowerCase()}
            </button>
          ))}
        </div>
      </div>
      {feedback ? <p className="notice notice--warn" role="alert">{feedback}</p> : null}

      <div className="split">
        <Panel title="Why this case exists">
          {(detail.dossier?.factors || []).map((factor) => (
            <FactorBar key={factor.rule_id} label={factor.rule_id + ' - ' + factor.name} contribution={factor.contribution} detail={factor.statement} />
          ))}
          <div className="row row--between" style={{ marginTop: '0.5rem' }}>
            <RiskBadge band={record.risk_score && record.risk_score >= 70 ? 'HIGH' : record.risk_score && record.risk_score >= 40 ? 'MEDIUM' : 'LOW'} score={record.risk_score ?? null} />
            <span className="muted mono">Sanctioned {formatCurrency(detail.dossier?.sanction_amount)} - spent {formatCurrency(detail.dossier?.expenditure)} - progress {formatNumber(detail.dossier?.progress_percent, 1)}%</span>
          </div>
          <ConfidenceMeter score={record.confidence_score ?? null} />
        </Panel>
        <Panel title="Verification checklist" description="Derived from the signals that fired on this work.">
          <ul className="stack" style={{ listStyle: 'none', padding: 0 }}>
            {record.checklist.map((item) => (
              <li key={item.id}>
                <label className="row">
                  <input type="checkbox" checked={item.done} onChange={() => toggleChecklist.mutate(record.checklist.map((entry) => entry.id === item.id ? { ...entry, done: !entry.done } : entry))} />
                  <span>{item.label}</span>
                </label>
              </li>
            ))}
          </ul>
          <h3>Recommended actions</h3>
          <ul>{(detail.dossier?.recommended_actions || []).map((action) => <li key={action}>{action}</li>)}</ul>
        </Panel>
      </div>

      <div className="split">
        <Panel title="Record an outcome" description={record.calibration_note}>
          {record.outcome ? <p className="notice">Outcome recorded: <strong>{record.outcome.replace(/_/g, ' ')}</strong> on {formatDateTime(record.outcome_recorded_at)}</p> : null}
          <label className="field">Outcome
            <select value={outcome} onChange={(event) => setOutcome(event.target.value)}>
              <option value="">Select an outcome</option>
              {detail.outcomes.map((value) => <option key={value} value={value}>{value.replace(/_/g, ' ')}</option>)}
            </select>
          </label>
          <button type="button" className="btn btn--primary" disabled={!outcome || recordOutcome.isPending} onClick={() => recordOutcome.mutate(outcome)}>Save outcome</button>
        </Panel>
        <Panel title="Notes and evidence">
          <label className="field">Add a note
            <textarea value={drafts[noteKey] || ''} onChange={(event) => setDraft(noteKey, event.target.value)} placeholder="What did you check, and what did you find?" />
          </label>
          <div className="btn-row">
            <button type="button" className="btn" disabled={!drafts[noteKey] || addNote.isPending} onClick={() => addNote.mutate(drafts[noteKey])}>Save note</button>
            <label className="btn">
              Attach evidence
              <input type="file" style={{ display: 'none' }} onChange={(event) => { const file = event.target.files?.[0]; if (file) uploadEvidence.mutate(file); }} />
            </label>
          </div>
          <ul>
            {detail.evidence.map((item) => (
              <li key={item.id}>{item.original_filename} <span className="muted mono">SHA-256 {item.checksum_sha256.slice(0, 16)}...</span></li>
            ))}
          </ul>
          {detail.evidence.length ? <p className="muted">{detail.evidence[0].authenticity_note}</p> : null}
        </Panel>
      </div>

      <Panel title="Case activity">
        <Timeline items={detail.timeline.map((item) => ({ id: item.id, title: item.title, meta: (item.actor ? item.actor + ' - ' : '') + formatDateTime(item.at), body: item.body || undefined }))} />
      </Panel>
      <TransparencyNote note={detail.dossier?.transparency_note} />
    </>
  );
}
