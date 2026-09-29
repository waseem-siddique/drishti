'use client';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { api, formatCurrency, formatNumber } from '@/lib/api';
import { DataTable, EmptyState, ErrorState, Panel, PriorityBadge, RiskBadge, Skeleton } from '@/components/ui';
import { useUiStore, type WorkFilters } from '@/state/uiStore';

type Row = {
  work_id: string; description?: string | null; state?: string | null; district?: string | null;
  category?: string | null; agency?: string | null; sanction_amount?: number | null;
  expenditure?: number | null; progress_percent?: number | null; status?: string | null;
  risk_score?: number | null; risk_band?: string | null; confidence_score?: number | null;
  priority?: string | null; priority_label?: string | null; signal_count?: number;
};

const FILTERS: Array<{ key: keyof WorkFilters; label: string; options?: string }> = [
  { key: 'search', label: 'Search' },
  { key: 'state', label: 'State', options: 'states' },
  { key: 'district', label: 'District', options: 'districts' },
  { key: 'category', label: 'Category', options: 'categories' },
  { key: 'agency', label: 'Agency', options: 'agencies' },
  { key: 'risk_band', label: 'Risk band', options: 'risk_bands' },
  { key: 'priority', label: 'Priority', options: 'priorities' },
  { key: 'status', label: 'Work status', options: 'statuses' },
];

export default function WorksPage() {
  const { filters, page, pageSize, sort, direction, hiddenColumns, setFilter, resetFilters, setPage, setSort, toggleColumn } = useUiStore();
  const options = useQuery({ queryKey: ['work-filters'], queryFn: () => api.get<Record<string, string[]>>('/works/filters') });

  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize), sort, direction });
  if (filters.search) params.set('search', filters.search);
  if (filters.state) params.set('state', filters.state);
  if (filters.district) params.set('district', filters.district);
  if (filters.category) params.set('category', filters.category);
  if (filters.agency) params.set('agency', filters.agency);
  if (filters.risk_band) params.set('risk_band', filters.risk_band);
  if (filters.priority) params.set('priority', filters.priority);
  if (filters.status) params.set('work_status', filters.status);

  const query = useQuery({
    queryKey: ['works', params.toString()],
    queryFn: () => api.get<{ items: Row[]; total: number; page: number; page_size: number; pages: number }>('/works?' + params.toString()),
  });

  const columns = [
    { key: 'priority', header: 'Priority', sortable: true, render: (row: Row) => row.priority ? <PriorityBadge priority={row.priority} label={row.priority_label} /> : <span className="muted">Not scored</span> },
    { key: 'work_id', header: 'Work ID', sortable: true, render: (row: Row) => <Link href={'/works/' + row.work_id} className="mono nowrap">{row.work_id}</Link> },
    { key: 'description', header: 'Description', render: (row: Row) => <span className="wrap">{row.description || '-'}</span> },
    { key: 'district', header: 'District', sortable: true, render: (row: Row) => row.district || '-' },
    { key: 'category', header: 'Category', sortable: true, render: (row: Row) => row.category || '-' },
    { key: 'agency', header: 'Agency', render: (row: Row) => row.agency || '-' },
    { key: 'sanction_amount', header: 'Sanctioned', sortable: true, numeric: true, render: (row: Row) => formatCurrency(row.sanction_amount) },
    { key: 'expenditure', header: 'Spent', sortable: true, numeric: true, render: (row: Row) => formatCurrency(row.expenditure) },
    { key: 'progress_percent', header: 'Progress %', sortable: true, numeric: true, render: (row: Row) => formatNumber(row.progress_percent, 1) },
    { key: 'risk_score', header: 'Risk', sortable: true, render: (row: Row) => <RiskBadge band={row.risk_band} score={row.risk_score ?? null} /> },
    { key: 'confidence_score', header: 'Confidence', sortable: true, numeric: true, render: (row: Row) => formatNumber(row.confidence_score, 1) },
    { key: 'signal_count', header: 'Signals', numeric: true, render: (row: Row) => formatNumber(row.signal_count ?? 0) },
  ];

  function exportCsv() {
    const rows = query.data?.items || [];
    const header = columns.map((column) => column.header).join(',');
    const body = rows.map((row) => [row.priority, row.work_id, JSON.stringify(row.description || ''), row.district, row.category,
      row.agency, row.sanction_amount, row.expenditure, row.progress_percent, row.risk_score, row.confidence_score, row.signal_count].join(','));
    const blob = new Blob([[header, ...body].join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'drishti-works-page-' + page + '.csv';
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <h1>Works explorer</h1>
      <Panel title="Filters" description="Filtering, sorting and pagination all happen in the database."
        actions={<><button type="button" className="btn" onClick={resetFilters}>Clear</button><button type="button" className="btn" onClick={exportCsv} disabled={!query.data?.items.length}>Export page as CSV</button></>}>
        <div className="filter-bar">
          {FILTERS.map((filter) => (
            <label key={filter.key} className="field">{filter.label}
              {filter.options ? (
                <select value={filters[filter.key]} onChange={(event) => setFilter(filter.key, event.target.value)}>
                  <option value="">All</option>
                  {(options.data?.[filter.options] || []).map((value) => <option key={value} value={value}>{value}</option>)}
                </select>
              ) : (
                <input type="search" value={filters[filter.key]} onChange={(event) => setFilter(filter.key, event.target.value)} placeholder="Work ID, description, agency" />
              )}
            </label>
          ))}
        </div>
        <details className="stack">
          <summary>Column visibility</summary>
          <div className="filter-bar">
            {columns.map((column) => (
              <label key={column.key} className="row">
                <input type="checkbox" checked={!hiddenColumns.includes(column.key)} onChange={() => toggleColumn(column.key)} />
                {column.header}
              </label>
            ))}
          </div>
        </details>
      </Panel>
      <Panel title={'Works' + (query.data ? ' (' + formatNumber(query.data.total) + ')' : '')}
        actions={query.data ? (
          <>
            <button type="button" className="btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
            <span className="muted nowrap">Page {query.data.page} of {Math.max(1, query.data.pages)}</span>
            <button type="button" className="btn" disabled={page >= query.data.pages} onClick={() => setPage(page + 1)}>Next</button>
          </>
        ) : undefined}>
        {query.isLoading ? <Skeleton rows={8} /> : query.error ? <ErrorState error={query.error} retry={() => query.refetch()} />
          : !query.data?.items.length ? <EmptyState title="No works match these filters" body="Widen the filters, or upload a dataset from the ingestion screen." />
          : <DataTable caption="MPLADS works" rows={query.data.items} rowKey={(row) => row.work_id} columns={columns}
              sort={sort} direction={direction} onSort={setSort} hidden={hiddenColumns} />}
      </Panel>
    </>
  );
}
