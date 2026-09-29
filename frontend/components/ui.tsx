'use client';
// Shared presentation components. Risk is never conveyed by colour alone: every badge
// carries a glyph and a text label as well.
import React from 'react';

export const RISK_GLYPH: Record<string, string> = { HIGH: '\u25B2', MEDIUM: '\u25C6', LOW: '\u25CF' };

export function RiskBadge({ band, score }: { band?: string | null; score?: number | null }) {
  const key = (band || 'LOW').toUpperCase();
  const cls = key === 'HIGH' ? 'badge badge--high' : key === 'MEDIUM' ? 'badge badge--medium' : 'badge badge--low';
  return (
    <span className={cls}>
      <span className="badge-glyph" aria-hidden="true">{RISK_GLYPH[key] || '\u25CF'}</span>
      {key} RISK{score === null || score === undefined ? '' : ' ' + score}
    </span>
  );
}

export function PriorityBadge({ priority, label }: { priority?: string | null; label?: string | null }) {
  const key = (priority || 'P3').toUpperCase();
  const cls = key === 'P1' ? 'badge badge--high' : key === 'P2' ? 'badge badge--medium' : 'badge badge--neutral';
  return <span className={cls}>{label || key}</span>;
}

export function CaseStatusBadge({ status, label }: { status?: string | null; label?: string | null }) {
  const key = (status || '').toUpperCase();
  const cls = key === 'ESCALATED' ? 'badge badge--high'
    : key === 'RESOLVED' || key === 'CLOSED' ? 'badge badge--low'
    : 'badge badge--neutral';
  return <span className={cls}>{label || key.replace(/_/g, ' ') || 'UNKNOWN'}</span>;
}

export function ConfidenceMeter({ score, label }: { score?: number | null; label?: string | null }) {
  const value = Math.max(0, Math.min(100, score ?? 0));
  return (
    <div className="stack">
      <div className="row row--between">
        <span className="muted">Confidence in this signal set</span>
        <strong>{score === null || score === undefined ? 'Not available' : value + ' / 100'}</strong>
      </div>
      <div className="meter" role="meter" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100} aria-label="Confidence">
        <span style={{ width: value + '%' }} />
      </div>
      {label ? <p className="muted">{label}</p> : null}
    </div>
  );
}

export function Kpi({ label, value, meta, tone }: { label: string; value: React.ReactNode; meta?: React.ReactNode; tone?: 'high' | 'medium' }) {
  const cls = tone === 'high' ? 'kpi kpi--high' : tone === 'medium' ? 'kpi kpi--medium' : 'kpi';
  return (
    <div className={cls}>
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}</span>
      {meta ? <span className="kpi-meta">{meta}</span> : null}
    </div>
  );
}

export function FactorBar({ label, contribution, detail }: { label: string; contribution: number; detail?: string }) {
  const width = Math.max(2, Math.min(100, contribution));
  return (
    <div className="factor-row">
      <div className="row row--between">
        <span>{label}</span>
        <span className="factor-contribution mono">+{contribution.toFixed(1)}</span>
      </div>
      <div className="factor-bar"><span style={{ width: width + '%' }} /></div>
      {detail ? <p className="muted">{detail}</p> : null}
    </div>
  );
}

export function Panel({ title, actions, children, description }: { title: string; actions?: React.ReactNode; children: React.ReactNode; description?: string }) {
  return (
    <section className="panel">
      <header className="panel-header">
        <div>
          <h2>{title}</h2>
          {description ? <p className="muted">{description}</p> : null}
        </div>
        {actions ? <div className="btn-row">{actions}</div> : null}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  );
}

export function EmptyState({ title, body, action }: { title: string; body?: string; action?: React.ReactNode }) {
  return (
    <div className="empty-state">
      <h3>{title}</h3>
      {body ? <p className="muted">{body}</p> : null}
      {action}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const message = error instanceof Error ? error.message : 'Something went wrong.';
  return (
    <div className="error-state" role="alert">
      <h3>This view could not load</h3>
      <p>{message}</p>
      {retry ? <button type="button" className="btn" onClick={retry}>Try again</button> : null}
    </div>
  );
}

export function Skeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="stack" aria-busy="true" aria-live="polite">
      <span className="visually-hidden">Loading</span>
      {Array.from({ length: rows }).map((_, index) => <div key={index} className="skeleton" />)}
    </div>
  );
}

export function Unavailable({ children }: { children?: React.ReactNode }) {
  return <span className="unavailable">{children || 'Not present in current dataset'}</span>;
}

export function TransparencyNote({ note }: { note?: string | null }) {
  return (
    <p className="transparency-note">
      {note || 'DRISHTI provides risk-based decision support. A risk score does not establish fraud or misconduct. Final determination requires authorized human verification.'}
    </p>
  );
}

export function Timeline({ items }: { items: Array<{ id: React.Key; title: string; meta?: string; body?: string }> }) {
  if (!items.length) return <EmptyState title="No activity recorded yet" />;
  return (
    <ol className="timeline">
      {items.map((item) => (
        <li key={item.id}>
          <strong>{item.title}</strong>
          {item.meta ? <span className="muted"> {item.meta}</span> : null}
          {item.body ? <p>{item.body}</p> : null}
        </li>
      ))}
    </ol>
  );
}

export type Column<T> = {
  key: string;
  header: string;
  sortable?: boolean;
  numeric?: boolean;
  render: (row: T) => React.ReactNode;
};

export function DataTable<T>({ columns, rows, rowKey, sort, direction, onSort, caption, hidden = [] }: {
  columns: Array<Column<T>>;
  rows: T[];
  rowKey: (row: T) => React.Key;
  sort?: string;
  direction?: 'asc' | 'desc';
  onSort?: (key: string) => void;
  caption: string;
  hidden?: string[];
}) {
  const visible = columns.filter((column) => !hidden.includes(column.key));
  return (
    <div className="table-scroll">
      <table className="data-table">
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            {visible.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={column.numeric ? 'num' : undefined}
                aria-sort={sort === column.key ? (direction === 'asc' ? 'ascending' : 'descending') : 'none'}
              >
                {column.sortable && onSort ? (
                  <button type="button" className="sort-button" onClick={() => onSort(column.key)}>
                    {column.header}
                    <span aria-hidden="true">{sort === column.key ? (direction === 'asc' ? ' \u2191' : ' \u2193') : ''}</span>
                  </button>
                ) : column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {visible.map((column) => (
                <td key={column.key} className={column.numeric ? 'num' : undefined}>{column.render(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
