'use client';
import Link from 'next/link';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, formatDateTime } from '@/lib/api';
import { EmptyState, ErrorState, Panel, PriorityBadge, Skeleton } from '@/components/ui';

type Alert = { id: number; title: string; body?: string | null; severity?: string | null; work_ref?: string | null; case_ref?: string | null; is_read: boolean; created_at: string };

export default function AlertsPage() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ['alerts'], queryFn: () => api.get<{ items: Alert[]; unread: number }>('/notifications') });
  const markRead = useMutation({
    mutationFn: (id: number) => api.patch('/notifications/' + id + '/read'),
    onSuccess: () => client.invalidateQueries({ queryKey: ['alerts'] }),
  });

  if (query.isLoading) return <Skeleton rows={6} />;
  if (query.error) return <ErrorState error={query.error} retry={() => query.refetch()} />;
  const data = query.data!;

  return (
    <>
      <h1>Alerts</h1>
      <Panel title={'Alert centre (' + data.unread + ' unread)'} description="Alerts are stored, not generated in the browser.">
        {data.items.length === 0 ? <EmptyState title="No alerts" body="New high-priority works and case assignments appear here." /> : (
          <ul className="stack" style={{ listStyle: 'none', padding: 0 }}>
            {data.items.map((item) => (
              <li key={item.id} className="panel">
                <div className="panel-body stack">
                  <div className="row row--between">
                    <strong>{item.title}</strong>
                    <span className="row">
                      {item.severity ? <PriorityBadge priority={item.severity === 'HIGH' ? 'P1' : 'P2'} label={item.severity} /> : null}
                      <span className="muted nowrap">{formatDateTime(item.created_at)}</span>
                    </span>
                  </div>
                  {item.body ? <p>{item.body}</p> : null}
                  <div className="btn-row">
                    {item.work_ref ? <Link className="btn" href={'/works/' + item.work_ref}>Open work</Link> : null}
                    {item.case_ref ? <Link className="btn" href={'/cases/' + item.case_ref}>Open case</Link> : null}
                    {!item.is_read ? <button type="button" className="btn" onClick={() => markRead.mutate(item.id)}>Mark as read</button> : <span className="muted">Read</span>}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </>
  );
}
