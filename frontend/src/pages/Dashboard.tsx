import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowUpDown, Eye, Paperclip, Plus, X } from 'lucide-react';
import '../components/WorkflowUi.css';
import { api } from '../services/api';
import type { Activity, Project, User } from '../types';

async function downloadDocument(url: string, name: string) {
  const response = await api.get(url, { responseType: 'blob' });
  const objectUrl = URL.createObjectURL(response.data);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = name;
  link.click();
  URL.revokeObjectURL(objectUrl);
}

const money = (value: string) => new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
}).format(Number(value || 0));

export default function Dashboard({ user }: { user: User }) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [selected, setSelected] = useState<Project | null>(null);
  const [page, setPage] = useState(1);
  const [create, setCreate] = useState(false);
  const summary = useQuery({
    queryKey: ['dashboard-summary', user.id],
    queryFn: async () => (await api.get('/dashboard/summary/')).data,
  });
  const workflowDashboard = useQuery({
    queryKey: ['workflow-dashboard', user.id],
    queryFn: async () => (await api.get('/workflow/dashboard/')).data,
  });
  const projects = useQuery({
    queryKey: ['projects', search, status, page, user.id],
    queryFn: async () => (await api.get('/projects/', {
      params: {
        search,
        current_status: status || undefined,
        page,
        ordering: '-updated_at',
      },
    })).data,
  });
  const departments = useQuery({
    queryKey: ['departments'],
    queryFn: async () => (await api.get('/departments/')).data.results || [],
  });
  const activities = useQuery({
    queryKey: ['activities', selected?.id, user.id],
    enabled: Boolean(selected),
    queryFn: async () => (await api.get(`/projects/${selected!.id}/activities/`)).data as Activity[],
  });
  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append('file', file);
      return api.post(`/projects/${selected!.id}/documents/`, form);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['activities', selected?.id, user.id] }),
  });
  const createProject = useMutation({
    mutationFn: (data: Record<string, string>) => api.post('/projects/', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] });
      setCreate(false);
    },
  });

  const rows: Project[] = projects.data?.results || [];
  const counts = summary.data || {
    total_projects: projects.data?.count || 0,
    active_projects: 0,
    pending_actions: 0,
    approved_projects: 0,
  };
  const admin = user.roles?.some(role => ['ADMIN', 'SUPER_ADMIN'].includes(role));
  const isApprover = user.roles?.some(role => ['SS', 'AS', 'HQ', 'DGS', 'IA_WING'].includes(role));
  const committeeAssignments = workflowDashboard.data?.committee_assignments || [];
  const pendingApprovals = workflowDashboard.data?.pending_approvals || [];
  const cards = admin
    ? [
      ['Total users', counts.total_users || 0],
      ['Pending user verification', counts.pending_user_verifications || 0],
      ['Total vendors', counts.total_vendors || 0],
      ['Pending vendor verification', counts.pending_vendor_verifications || 0],
      ['Total projects', counts.total_projects],
      ['Active projects', counts.active_projects],
    ]
    : isApprover
      ? [
        ['Total projects', counts.total_projects],
        ['Active projects', counts.active_projects],
        ['Approved projects', counts.approved_projects],
      ]
      : [
      ['Total projects', counts.total_projects],
      ['My active projects', counts.active_projects],
      ['Pending actions', counts.pending_actions],
      ['Approved projects', counts.approved_projects],
    ];

  return (
    <>
      <div className="content">
        <div className="heading">
          <div>
            <h1>{admin ? 'Operations overview' : 'My projects'}</h1>
            <div className="muted">Track procurement activity and project progress.</div>
          </div>
          <button className="button primary" onClick={() => setCreate(true)}>
            <Plus size={16} style={{ verticalAlign: 'middle', marginRight: 7 }} />
            New project
          </button>
        </div>
        <div className="cards">
          {cards.map(([title, value]) => (
            <div className="card" key={title}>
              <div className="card-label">{title}</div>
              <div className="card-value">{value}</div>
            </div>
          ))}
        </div>
        {!!committeeAssignments.length && (
          <section className="panel" style={{ marginBottom: 16 }}>
            <div className="panel-head">
              <div>
                <b>My committee duties</b>
                <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  Committee membership is separate from any approval authority you hold.
                </div>
              </div>
            </div>
            <div style={{ display: 'grid', gap: 10, padding: 16 }}>
              {committeeAssignments.map((assignment: Record<string, any>) => (
                <article className="card" key={assignment.committee_id}>
                  <div className="project-tsc-summary">
                    <div>
                      <b>{assignment.project_code} · {assignment.project_title}</b>
                      <div className="muted">
                        {assignment.committee_name} · {assignment.committee_type} committee member
                        {assignment.is_chair ? ' · Chair' : ''}
                      </div>
                    </div>
                    <Link className="button project-details-button" to={`/projects/${assignment.project_id}`}>
                      Open committee project
                    </Link>
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}
        {isApprover && (
          <section className="panel" style={{ marginBottom: 16 }}>
            <div className="panel-head">
              <div>
                <b>My approval duties</b>
                <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  These are approval assignments, separate from committee membership.
                </div>
              </div>
            </div>
            {workflowDashboard.isLoading ? (
              <div className="empty">Loading approval duties…</div>
            ) : workflowDashboard.isError ? (
              <div role="alert" className="empty">Could not load approval duties. Please retry.</div>
            ) : pendingApprovals.length ? (
              <div style={{ display: 'grid', gap: 10, padding: 16 }}>
                {pendingApprovals.map((approval: Record<string, any>) => {
                  const dutyLabels: Record<string, string> = {
                    TSC_FORMATION: 'SS · TSC formation approver',
                    TEC_FORMATION: 'SS · TEC formation approver',
                    TAC_FORMATION: 'SS · TAC formation approver',
                    TSC_REPORT_LEVEL3: 'DGS · TSC report approver',
                    TEC_REPORT: 'HQ · TEC report approver',
                    TENDER_DRAFT: 'IA Wing · Tender draft approver',
                  };
                  const dutyLabel = approval.submission_type === 'TSC_REPORT'
                    ? `${approval.approver_role || 'AS / HQ'} · TSC report approver`
                    : dutyLabels[approval.submission_type] || approval.title;
                  return (
                    <article className="card" key={approval.id}>
                      <div className="project-tsc-summary">
                        <div>
                          <b>{approval.project_code} · {approval.project?.title}</b>
                          <div className="muted">
                            {dutyLabel}
                            {' · '}{approval.step_status === 'QUERY' ? 'Awaiting submitter response' : 'Approval required'}
                          </div>
                        </div>
                        <Link className="button project-details-button" to={`/projects/${approval.project_id}`}>
                          Review project
                        </Link>
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="empty">No approval actions are currently assigned to your approver roles.</div>
            )}
          </section>
        )}
        <div className="panel">
          <div className="panel-head">
            <div>
              <b>Procurement projects</b>
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Recent projects you can access</div>
            </div>
            <div className="toolbar">
              <input
                placeholder="Search projects…"
                value={search}
                onChange={event => {
                  setSearch(event.target.value);
                  setPage(1);
                }}
              />
              <select value={status} onChange={event => setStatus(event.target.value)}>
                <option value="">All statuses</option>
                {['DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'COMMITTEE_REVIEW', 'PENDING_APPROVAL', 'APPROVED', 'RETURNED', 'REJECTED'].map(item => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </div>
          </div>
          {projects.isLoading ? <div className="empty">Loading projects…</div> :
            projects.isError ? <div className="empty">Could not load projects. Please retry.</div> : (
              <>
                <table>
                  <thead>
                    <tr>
                      <th>PROJECT ID</th><th>PROJECT TITLE</th><th>DEPARTMENT</th>
                      <th>ESTIMATED AMOUNT</th><th>STATUS</th><th>LAST UPDATED</th><th>ACTION <ArrowUpDown size={12} /></th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map(project => (
                      <tr key={project.id}>
                        <td>
                          <Link className="project-id-link" to={`/projects/${project.id}`}>
                            {project.project_code}
                          </Link>
                        </td>
                        <td><b>{project.title}</b></td>
                        <td>{project.department_name}</td>
                        <td>{money(project.estimated_amount)}</td>
                        <td><span className="status">{project.current_status.replace(/_/g, ' ')}</span></td>
                        <td>{new Date(project.updated_at).toLocaleDateString()}</td>
                        <td>
                          <div className="project-actions">
                            <button
                              aria-label={`View ${project.project_code} project activity`}
                              title="View project activity"
                              className="icon-button"
                              onClick={() => setSelected(project)}
                            >
                              <Eye size={16} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {rows.length === 0 && <div className="empty">No projects found. Create a project to get started.</div>}
                <div className="project-pagination">
                  <small className="muted">Showing {rows.length} of {projects.data?.count || 0}</small>
                  <div>
                    <button className="icon-button" disabled={!projects.data?.previous} onClick={() => setPage(page - 1)}>Previous</button>{' '}
                    <button className="icon-button" disabled={!projects.data?.next} onClick={() => setPage(page + 1)}>Next</button>
                  </div>
                </div>
              </>
            )}
        </div>
      </div>

      {selected && (
        <>
          <div className="drawer-backdrop" onClick={() => setSelected(null)} />
          <aside className="drawer">
            <div className="drawer-head">
              <div className="project-drawer-title">
                <div>
                  <div className="muted">{selected.project_code} · {selected.department_name}</div>
                  <h2>{selected.title}</h2>
                </div>
                <button aria-label="Close project activity" className="icon-button" onClick={() => setSelected(null)}>
                  <X size={17} />
                </button>
              </div>
              <div className="project-drawer-meta">
                <span><small>Estimated amount</small><b>{money(selected.estimated_amount)}</b></span>
                <span><small>Project status</small><b className="status">{selected.current_status.replace(/_/g, ' ')}</b></span>
              </div>
              <div className="muted" style={{ marginTop: 12 }}>
                Created by {selected.created_by_name} · {new Date(selected.created_at).toLocaleDateString()}
              </div>
            </div>
            <div className="drawer-body">
              <h3 className="project-drawer-section-title">Project activity</h3>
              {activities.isLoading ? <div className="muted">Loading activity…</div> :
                activities.isError ? <div role="alert" className="workflow-alert error">Unable to load project activity.</div> :
                  activities.data?.length ? activities.data.map(activity => (
                    <div className="timeline-item" key={activity.id}>
                      <div className="project-activity-heading">
                        <b style={{ fontSize: 13 }}>{activity.actor_name}</b>
                        <span className="muted" style={{ fontSize: 11 }}>{new Date(activity.created_at).toLocaleString()}</span>
                      </div>
                      <p>{activity.message}</p>
                      <span className="status">{activity.activity_type.replace(/_/g, ' ')}</span>
                      {activity.documents?.map(document => (
                        <div key={document.id}>
                          <button className="icon-button" onClick={() => downloadDocument(document.url, document.name)} style={{ marginTop: 8 }}>
                            Download {document.name}
                          </button>
                        </div>
                      ))}
                    </div>
                  )) : <div className="muted">No activity yet.</div>}
            </div>
            <div className="project-drawer-upload">
              <label className="icon-button project-drawer-upload-button">
                <Paperclip size={16} />
                <span>{upload.isPending ? 'Uploading document…' : 'Upload project document'}</span>
                <input
                  hidden
                  type="file"
                  accept="application/pdf,.pdf"
                  disabled={upload.isPending}
                  onChange={event => {
                    const file = event.target.files?.[0];
                    if (file) upload.mutate(file);
                    event.target.value = '';
                  }}
                />
              </label>
              {upload.isError && <small style={{ color: '#b42318' }}>PDF upload failed. Check that the file is under 10 MB.</small>}
            </div>
          </aside>
        </>
      )}
      {create && (
        <>
          <div className="drawer-backdrop" onClick={() => setCreate(false)} />
          <CreateProject
            onClose={() => setCreate(false)}
            departments={departments.data || []}
            busy={createProject.isPending}
            error={createProject.isError}
            onSave={data => createProject.mutate(data)}
          />
        </>
      )}
    </>
  );
}

function CreateProject({
  onClose,
  departments,
  busy,
  error,
  onSave,
}: {
  onClose: () => void;
  departments: Array<{ id: string; department_name: string }>;
  busy: boolean;
  error: boolean;
  onSave: (data: Record<string, string>) => void;
}) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [department, setDepartment] = useState('');
  const [amount, setAmount] = useState('');
  return (
    <aside className="drawer" style={{ padding: 26 }}>
      <div className="heading">
        <h2>New procurement project</h2>
        <button onClick={onClose} className="icon-button"><X size={16} /></button>
      </div>
      <p className="muted">Provide the initial details. You can add context in the project timeline.</p>
      <form onSubmit={event => {
        event.preventDefault();
        onSave({ title, description, department, estimated_amount: amount });
      }}>
        <label className="muted">Project title</label>
        <input required value={title} onChange={event => setTitle(event.target.value)} className="project-form-control" />
        <label className="muted">Department</label>
        <select required value={department} onChange={event => setDepartment(event.target.value)} className="project-form-control">
          <option value="">Select department</option>
          {departments.map(item => <option key={item.id} value={item.id}>{item.department_name}</option>)}
        </select>
        <label className="muted">Estimated amount (INR)</label>
        <input required type="number" min="0" step="0.01" value={amount} onChange={event => setAmount(event.target.value)} className="project-form-control" />
        <label className="muted">Description</label>
        <textarea value={description} onChange={event => setDescription(event.target.value)} className="project-form-description" />
        {error && <p style={{ color: '#b42318' }}>Could not create project. Check your department and try again.</p>}
        <button className="button primary" disabled={busy}>{busy ? 'Creating…' : 'Create project'}</button>
      </form>
    </aside>
  );
}
