import { FormEvent, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft } from 'lucide-react';
import { api } from '../services/api';
import MemberSelector from '../components/MemberSelector';
import type { User } from '../types';
import Workflow from './Workflow';

type Row = Record<string, any>;

function rowsFrom(data: any): Row[] {
  return Array.isArray(data) ? data : data?.results || [];
}

async function fetchAll(path: string) {
  const rows: Row[] = [];
  let url: string | null = path;
  while (url) {
    const pageResponse: { data: { results?: Row[]; next?: string | null } } = await api.get(
      url,
      { params: url === path ? { page_size: 100 } : undefined },
    );
    rows.push(...rowsFrom(pageResponse.data));
    url = pageResponse.data.next || null;
  }
  return rows;
}

function errorMessage(error: any) {
  const data = error.response?.data;
  if (typeof data === 'string') return data;
  if (data?.detail) return data.detail;
  if (data) return Object.entries(data).map(([key, value]) => `${key}: ${String(value)}`).join(' ');
  return 'The request failed. Please try again.';
}

function money(value: string) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(Number(value || 0));
}

export default function ProjectDetail({ user }: { user: User }) {
  const { projectId = '' } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const admin = user.roles?.some(role => ['ADMIN', 'SUPER_ADMIN'].includes(role)) || false;
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const projectQuery = useQuery({
    queryKey: ['project', projectId, user.id],
    queryFn: async () => (await api.get(`/projects/${projectId}/`)).data,
    enabled: Boolean(projectId),
  });
  const activitiesQuery = useQuery({
    queryKey: ['activities', projectId, user.id],
    queryFn: async () => (await api.get(`/projects/${projectId}/activities/`)).data,
    enabled: Boolean(projectId),
  });
  const committeesQuery = useQuery({
    queryKey: ['workflow-committees', user.id],
    queryFn: () => fetchAll('/workflow/committees/'),
  });
  const usersQuery = useQuery({
    queryKey: ['workflow-users', user.id],
    enabled: admin,
    queryFn: async () => (await fetchAll('/users/')).filter(
        (person: Row) => person.is_active && person.verification_status === 'VERIFIED',
    ),
  });

  useEffect(() => {
    if (!location.hash || projectQuery.isLoading) return;
    requestAnimationFrame(() => {
      document.getElementById(location.hash.slice(1))?.scrollIntoView({ behavior: 'smooth' });
    });
  }, [location.hash, projectQuery.isLoading, projectQuery.data]);

  const projectCommittees = rowsFrom(committeesQuery.data).filter(
    (committee: Row) => committee.project === projectId,
  );
  const tsc = projectCommittees.find(
    (committee: Row) => committee.committee_type === 'TSC' && committee.status !== 'REJECTED',
  );
  const createTSC = useMutation({
    mutationFn: (data: FormData) => api.post('/workflow/committees/', data),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workflow-committees'] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-submissions'] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['activities', projectId, user.id] }),
      ]);
      setError('');
      setNotice('TSC sent to SS for approval. It will be formed only after approval.');
    },
    onError: (requestError: any) => {
      setNotice('');
      setError(errorMessage(requestError));
    },
  });
  function handleCreateTSC(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const memberIds = formData.getAll('member_ids').map(String);
    const chair = String(formData.get('chair') || '');
    if (!memberIds.length || !memberIds.includes(chair)) {
      setNotice('');
      setError('Select at least one member and make sure the chair is included in the member list.');
      return;
    }
    formData.set('project', projectId);
    formData.set('committee_type', 'TSC');
    formData.set('chair', chair);
    createTSC.mutate(formData);
  }

  if (projectQuery.isLoading) return <div className="empty">Loading project details…</div>;
  if (projectQuery.isError || !projectQuery.data) {
    return <div className="content"><div className="empty">Could not load this project. It may not exist or you may not have access.</div></div>;
  }

  const project = projectQuery.data;
  const employees = rowsFrom(usersQuery.data);

  return (
    <div className="content">
      <div className="heading" style={{ justifyContent: 'space-between', gap: 12 }}>
        <div>
          <Link className="project-back-link" to="/projects"><ArrowLeft size={15} /> Back to projects</Link>
          <h1 style={{ marginTop: 12 }}>{project.title}</h1>
          <div className="muted">{project.project_code}</div>
        </div>
        <span className="status">{project.current_status.replaceAll('_', ' ')}</span>
      </div>

      {error && <div role="alert" className="workflow-alert error">{error}</div>}
      {notice && <div role="status" className="workflow-alert success">{notice}</div>}

      <section className="panel project-detail-panel">
        <div className="panel-head"><b>Project details</b></div>
        <dl className="project-detail-grid">
          <div><dt>Project ID</dt><dd>{project.project_code}</dd></div>
          <div><dt>Department</dt><dd>{project.department_name || '—'}</dd></div>
          <div><dt>Estimated amount</dt><dd>{money(project.estimated_amount)}</dd></div>
          <div><dt>Created by</dt><dd>{project.created_by_name || '—'}</dd></div>
          <div><dt>Created on</dt><dd>{new Date(project.created_at).toLocaleDateString()}</dd></div>
          <div><dt>Last updated</dt><dd>{new Date(project.updated_at).toLocaleDateString()}</dd></div>
          <div className="project-description"><dt>Description</dt><dd>{project.description || 'No description provided.'}</dd></div>
        </dl>
      </section>

      {(admin || tsc) && (
        <section className="panel project-tsc-panel">
          <div className="panel-head">
            <div>
              <b>{tsc ? 'TSC formation status' : 'Next step: Propose the TSC'}</b>
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                Select committee members and designate one of them as the chair. SS approval is required before the TSC is formed.
              </div>
            </div>
          </div>
          {committeesQuery.isError ? (
            <div className="workflow-panel-content" role="alert">Could not load this project’s committees.</div>
          ) : tsc ? (
            <div className="workflow-panel-content">
              <div className="project-tsc-summary">
                <div>
                  <b>{tsc.committee_name}</b>
                  <div className="muted">Chair: {tsc.chair_name || 'Not set'}{tsc.chair_employee_id ? ` (${tsc.chair_employee_id})` : ''} · Members: {tsc.members?.length || 0}</div>
                  {tsc.members?.length > 0 && (
                    <ul className="project-tsc-member-list" style={{ margin: '12px 0 0', paddingLeft: 18 }}>
                      {tsc.members.map((member: Row) => (
                        <li key={member.id}>
                          {member.name}
                          {member.employee_id ? ` (${member.employee_id})` : ''}
                          {member.designation ? ` · ${member.designation}` : ''}
                          {member.user === tsc.chair && ' · Chair'}
                          {member.roles?.some((role: string) => role === 'ADMIN' || role === 'SUPER_ADMIN') && ' · Admin'}
                        </li>
                      ))}
                    </ul>
                  )}
                  {tsc.status === 'SUBMITTED' && (
                    <div className="muted">Awaiting SS approval. The TSC is not active yet.</div>
                  )}
                  {tsc.status === 'ACTIVE' && (
                    <div className="muted">SS approved this TSC; the committee is now formed.</div>
                  )}
                </div>
                <span className="status">{tsc.status}</span>
              </div>
            </div>
          ) : admin ? (
            <form className="project-tsc-form" onSubmit={handleCreateTSC}>
              <label>
                Committee name
                <input name="committee_name" defaultValue="Technical Specification Committee" required />
              </label>
              <MemberSelector
                employees={employees}
                label="TSC members"
                help="Select any members; the chair must also be selected."
                ariaLabel="TSC member"
              />
              <label>
                TSC chair
                <select name="chair" required defaultValue="">
                  <option value="" disabled>Select chair</option>
                  {employees.map((person: Row) => (
                    <option key={person.id} value={person.id}>
                      {person.name}{person.employee_id ? ` (${person.employee_id})` : ''}
                      {person.roles?.some((role: string) => role === 'ADMIN' || role === 'SUPER_ADMIN') ? ' · Admin' : ''}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Supporting TSC formation PDF <span className="muted">(optional, max 10 MB)</span>
                <input name="file" type="file" accept="application/pdf,.pdf" />
              </label>
              <div className="project-tsc-submit">
                <button className="button primary" disabled={createTSC.isPending || usersQuery.isLoading || !employees.length}>
                  {createTSC.isPending ? 'Sending for approval…' : 'Send TSC to SS for approval'}
                </button>
                {usersQuery.isLoading && <span className="muted">Loading eligible employees…</span>}
                {!usersQuery.isLoading && !employees.length && <span className="muted">No active, verified employees are available.</span>}
              </div>
              <small className="muted">The chair must also be selected as a committee member. The PDF is optional and will be available to SS with the approval request. The TSC becomes active only after approval.</small>
            </form>
          ) : null}
        </section>
      )}

      <Workflow user={user} projectId={projectId} />

      <section className="panel">
        <div className="panel-head"><b>Project activity</b></div>
        <div className="project-activity-list">
          {activitiesQuery.isLoading ? <div className="empty">Loading activity…</div> :
            activitiesQuery.isError ? <div className="empty">Could not load project activity.</div> :
              rowsFrom(activitiesQuery.data).length ? rowsFrom(activitiesQuery.data).map((activity: Row) => (
                <article className="project-activity" key={activity.id}>
                  <div className="project-activity-heading">
                    <b>{activity.actor_name}</b>
                    <span className="muted">{new Date(activity.created_at).toLocaleString()}</span>
                  </div>
                  <p>{activity.message}</p>
                  <small className="muted">{activity.activity_type.replaceAll('_', ' ')}</small>
                </article>
              )) : <div className="empty">No project activity yet.</div>}
        </div>
      </section>
      {!admin && <div className="muted" style={{ marginTop: 16 }}>TSC formation is managed by an administrator.</div>}
      <button className="icon-button" style={{ marginTop: 16 }} onClick={() => navigate('/projects')}>Return to projects</button>
    </div>
  );
}
