import { FormEvent, Fragment, useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../services/api';
import type { User } from '../types';
import ApprovalInbox from '../components/ApprovalInbox';
import MemberSelector from '../components/MemberSelector';

type Row = Record<string, any>;

const stageTypes = [
  'TSC_FORMATION',
  'TSC_REPORT',
  'TSC_REPORT_LEVEL3',
  'TENDER_DRAFT',
  'TEC_FORMATION',
  'TEC_REPORT',
  'VENDOR_QUALIFICATION',
  'TAC_FORMATION',
  'TAC_FINANCIAL_BIDS',
  'TAC_FINAL_REPORT',
  'VENDOR_SELECTION',
];

const currentSubmissionTypes = new Set([
  'TSC_FORMATION',
  'TSC_REPORT',
  'TSC_REPORT_LEVEL3',
  'TEC_REPORT',
  'TENDER_DRAFT',
  'TEC_FORMATION',
  'TAC_FORMATION',
]);

function messageFromError(error: any) {
  const data = error.response?.data;
  if (typeof data === 'string') return data;
  if (data?.detail) return data.detail;
  if (data) return Object.entries(data).map(([key, value]) => `${key}: ${String(value)}`).join(' ');
  return 'The request failed. Please try again.';
}

function rowsFrom(data: any): Row[] {
  return Array.isArray(data) ? data : data?.results || [];
}

async function fetchAll(path: string) {
  const rows: Row[] = [];
  let url: string | null = path;
  while (url) {
    const data = await loadPage(url);
    rows.push(...rowsFrom(data));
    const nextPage: string | null = data.next || null;
    url = nextPage;
  }
  return rows;
}

async function loadPage(url: string): Promise<{ results?: Row[]; next?: string | null }> {
  const response = await api.get<{ results?: Row[]; next?: string | null }>(url);
  return response.data;
}

function dateLabel(value: string | null) {
  return value ? new Date(`${value}T00:00:00`).toLocaleDateString() : 'Not scheduled';
}

function latestRevision(rows: Row[]) {
  return rows.reduce(
    (latest: Row | null, item: Row) =>
      !latest || item.revision > latest.revision ? item : latest,
    null,
  );
}

function workflowTypeLabel(type: string) {
  const labels: Record<string, string> = {
    TSC_FORMATION: 'TSC formation · SS approval',
    TSC_REPORT: 'TSC report · AS → HQ approval',
    TSC_REPORT_LEVEL3: 'TSC report · DGS approval',
    TEC_REPORT: 'TEC final report · HQ approval',
    TENDER_DRAFT: 'Tender draft · IA Wing approval',
    TEC_FORMATION: 'TEC formation · SS approval',
    VENDOR_QUALIFICATION: 'Qualify vendors · Admin',
    TAC_FORMATION: 'TAC formation · SS approval',
    TAC_FINANCIAL_BIDS: 'Admin selects top vendors · financial bids for TAC',
    TAC_FINAL_REPORT: 'TAC final report · chair submission',
    VENDOR_SELECTION: 'Final vendor selection · Admin',
  };
  return labels[type] || type.replace(/_/g, ' ');
}

function timelineStatusLabel(status: string) {
  const labels: Record<string, string> = {
    COMPLETED_LATE: 'Completed late',
    AWAITING_APPROVAL: 'Awaiting tender approval',
    AWAITING_REVISION: 'Tender revision required',
    NOT_TRACKED: 'Not tracked',
  };
  return labels[status] || status.replace(/_/g, ' ');
}

function submissionTitleLabel(submission: Row) {
  if (submission.submission_type === 'TSC_REPORT') return 'TSC Report — AS/HQ Review';
  if (submission.submission_type === 'TSC_REPORT_LEVEL3') return 'TSC Report — DGS Review';
  if (submission.submission_type === 'TEC_REPORT') return 'TEC Final Report — HQ Review';
  return submission.title;
}

async function downloadFile(url: string, name: string) {
  const response = await api.get(url, { responseType: 'blob' });
  const objectUrl = URL.createObjectURL(response.data);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = name;
  link.click();
  URL.revokeObjectURL(objectUrl);
}

export default function Workflow({ user, projectId }: { user: User; projectId?: string }) {
  const queryClient = useQueryClient();
  const admin = user.roles?.some(role => ['ADMIN', 'SUPER_ADMIN'].includes(role)) || false;
  const projectScoped = Boolean(projectId);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [editingFormationSubmissionId, setEditingFormationSubmissionId] = useState<string | null>(null);
  const [respondingTscReportId, setRespondingTscReportId] = useState<string | null>(null);
  const [tenderSupersedesId, setTenderSupersedesId] = useState('');
  const dashboard = useQuery({
    queryKey: ['workflow-dashboard', user.id],
    queryFn: async () => (await api.get('/workflow/dashboard/')).data,
  });
  const stagesQuery = useQuery({
    queryKey: ['workflow-stages', user.id],
    queryFn: () => fetchAll('/workflow/stages/'),
  });
  const committeesQuery = useQuery({
    queryKey: ['workflow-committees', user.id],
    queryFn: () => fetchAll('/workflow/committees/'),
  });
  const submissionsQuery = useQuery({
    queryKey: ['workflow-submissions', user.id],
    queryFn: () => fetchAll('/workflow/submissions/'),
  });
  const tscDocumentsQuery = useQuery({
    queryKey: ['workflow-tsc-documents', user.id],
    queryFn: () => fetchAll('/workflow/tsc-documents/'),
  });
  const usersQuery = useQuery({
    queryKey: ['workflow-users', user.id],
    enabled: admin,
    queryFn: () => fetchAll('/users/'),
  });
  const action = useMutation({
    mutationFn: ({ method = 'post', url, data }: { method?: string; url: string; data?: any }) =>
      api.request({ method, url, data }),
    onSuccess: async (response) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workflow-dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-stages'] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-committees'] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-submissions'] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-tsc-documents'] }),
        queryClient.invalidateQueries({ queryKey: ['projects'] }),
        queryClient.invalidateQueries({ queryKey: ['notifications'] }),
      ]);
      setError('');
      const committee = response.data;
      setNotice(committee?.submission_type === 'TENDER_DRAFT'
        ? 'Tender draft sent to IA Wing for approval.'
        : committee?.submission_type === 'TSC_REPORT'
          ? 'TSC report sent to AS for approval.'
          : committee?.committee_type === 'TSC' && committee?.status === 'SUBMITTED'
            ? 'TSC sent to SS for approval. It will be formed only after approval.'
            : committee?.committee_type === 'TAC' && committee?.status === 'SUBMITTED'
              ? 'TAC sent to SS for approval. Members will have project access after approval.'
            : 'Saved.');
    },
    onError: (requestError: any) => {
      setNotice('');
      setError(messageFromError(requestError));
    },
  });

  const stages: Row[] = (dashboard.data?.stages || [])
    .filter((stage: Row) =>
      (!projectId || stage.project === projectId) && stageTypes.includes(stage.stage_type),
    )
    .sort((left: Row, right: Row) =>
      stageTypes.indexOf(left.stage_type) - stageTypes.indexOf(right.stage_type),
    );
  const timelineRows = stages.flatMap((stage: Row) => [
    { ...stage, timeline_key: stage.id, timeline_details: '', is_milestone: false },
    ...(stage.timeline_milestones || []).map((milestone: Row) => ({
      id: `${stage.id}-${milestone.key}`,
      timeline_key: `${stage.id}-${milestone.key}`,
      project_code: stage.project_code,
      stage_type: milestone.title,
      status: milestone.status,
      planned_start: null,
      due_date: milestone.due_date,
      completed_at: milestone.completed_at,
      timeline_details: milestone.details,
      is_milestone: true,
    })),
  ]);
  const productArrivalIndex = timelineRows.findIndex(
    (row: Row) => row.is_milestone && row.timeline_key.endsWith('-PRODUCT_ARRIVAL'),
  );
  if (productArrivalIndex !== -1) {
    const [productArrival] = timelineRows.splice(productArrivalIndex, 1);
    timelineRows.push(productArrival);
  }
  const projectCommittees = rowsFrom(committeesQuery.data).filter((committee: Row) =>
    !projectId || committee.project === projectId,
  );
  const committees = projectCommittees.filter((committee: Row) =>
    committee.committee_type === 'TSC',
  );
  const projectTscCommittee = committees.find(
    (committee: Row) => !projectId || committee.project === projectId,
  );
  const projectTecCommittee = projectCommittees.find(
    (committee: Row) => committee.committee_type === 'TEC',
  );
  const projectTacCommittee = projectCommittees.find(
    (committee: Row) =>
      committee.committee_type === 'TAC' && committee.status !== 'REJECTED',
  );
  const isCommitteeMember = (committee: Row) =>
    committee.chair === user.id
    || (committee.members || []).some((member: Row) => member.user === user.id);
  const myTscCommittees = committees.filter((committee: Row) =>
    committee.committee_type === 'TSC'
    && committee.status === 'ACTIVE'
    && isCommitteeMember(committee),
  );
  const myTscChairCommittees = myTscCommittees.filter(
    (committee: Row) => committee.chair === user.id,
  );
  const myTecCommittees = projectCommittees.filter((committee: Row) =>
    committee.committee_type === 'TEC'
    && committee.status === 'ACTIVE'
    && isCommitteeMember(committee),
  );
  const employees = rowsFrom(usersQuery.data).filter(
    (person: Row) => person.is_active && person.verification_status === 'VERIFIED',
  );
  const stageIds = new Set(stages.map((stage: Row) => stage.id));
  const submissions = rowsFrom(submissionsQuery.data).filter((submission: Row) =>
    currentSubmissionTypes.has(submission.submission_type)
    && (!projectId || stageIds.has(submission.stage)),
  );
  const tenderDraftStages = stages.filter(
    (stage: Row) => stage.stage_type === 'TENDER_DRAFT',
  );
  const tenderDraftSubmissions = submissions.filter(
    (submission: Row) => submission.submission_type === 'TENDER_DRAFT',
  );
  const latestTenderDraft = latestRevision(tenderDraftSubmissions);
  const revisableTenderDrafts = tenderDraftSubmissions.filter(
    (submission: Row) => ['NEEDS_RESPONSE', 'REJECTED'].includes(submission.status),
  );
  const selectedTenderSupersedes = revisableTenderDrafts.find(
    (submission: Row) => submission.id === tenderSupersedesId,
  );
  const tscChairCommittee = myTscChairCommittees.length === 1
    ? myTscChairCommittees[0]
    : null;
  const canSubmitDgsReport = admin
    || Boolean(tscChairCommittee && tscChairCommittee.id === projectTscCommittee?.id);
  const tscReportSubmissions = submissions.filter((submission: Row) =>
    submission.submission_type === 'TSC_REPORT'
    && submission.committee === projectTscCommittee?.id,
  );
  const latestTscReport = latestRevision(tscReportSubmissions);
  const tscReportApproval = latestTscReport?.approval_requests?.[0];
  const asReportStep = tscReportApproval?.steps?.find(
    (step: Row) => step.approver_role === 'AS',
  );
  const hqTscReportStep = tscReportApproval?.steps?.find(
    (step: Row) => step.approver_role === 'HQ',
  );
  const dgsTscReportSubmissions = submissions.filter((submission: Row) =>
    submission.submission_type === 'TSC_REPORT_LEVEL3'
    && submission.committee === projectTscCommittee?.id,
  );
  const latestDgsTscReport = latestRevision(dgsTscReportSubmissions);
  const tecReportSubmissions = submissions.filter((submission: Row) =>
    submission.submission_type === 'TEC_REPORT'
    && submission.committee === projectTecCommittee?.id,
  );
  const latestTecReport = latestRevision(tecReportSubmissions);
  const formationSubmissions = submissions.filter(
    (submission: Row) => submission.submission_type === 'TSC_FORMATION',
  );
  const tecFormationSubmissions = submissions.filter(
    (submission: Row) => submission.submission_type === 'TEC_FORMATION',
  );
  const tacFormationSubmissions = submissions.filter(
    (submission: Row) => submission.submission_type === 'TAC_FORMATION',
  );
  const latestFormation = latestRevision(formationSubmissions);
  const tscFormationComplete = projectTscCommittee?.status === 'ACTIVE'
    && latestFormation?.status === 'APPROVED';
  const asReportComplete = asReportStep
    ? asReportStep.status === 'APPROVED'
    : latestTscReport?.status === 'APPROVED';
  const hqTscReportComplete = hqTscReportStep
    ? hqTscReportStep.status === 'APPROVED'
    : latestTscReport?.status === 'APPROVED';
  const dgsReportComplete = hqTscReportComplete
    && latestDgsTscReport?.status === 'APPROVED';
  const tenderDraftComplete = dgsReportComplete && latestTenderDraft?.status === 'APPROVED';
  const projectVendorsQuery = useQuery({
    queryKey: ['project-vendors', projectId, user.id],
    queryFn: async () => (await api.get(`/projects/${projectId}/vendors/`)).data,
    enabled: projectScoped && admin && tenderDraftComplete,
  });
  const qualificationQuery = useQuery({
    queryKey: ['qualified-vendors', projectId],
    queryFn: async () => (await api.get(`/projects/${projectId}/qualified-vendors/`)).data,
    enabled: projectScoped && admin,
  });
  const selectedProjectVendors: Row[] = projectVendorsQuery.data?.vendors || [];
  const allSelectedVendorsDispatched = selectedProjectVendors.length > 0
    && selectedProjectVendors.every((vendor: Row) =>
      ['TENDER_SENT', 'BID_RECEIVED'].includes(vendor.participation_status),
    );
  const latestTecFormation = latestRevision(tecFormationSubmissions);
  const tecFormationComplete = projectTecCommittee?.status === 'ACTIVE'
    && latestTecFormation?.status === 'APPROVED';
  const tecReportStage = stages.find(
    (stage: Row) => stage.stage_type === 'TEC_REPORT',
  );
  const tecReportComplete = tecReportStage?.status === 'COMPLETED';
  const qualificationComplete = qualificationQuery.data?.qualification_complete;
  const tacFinancialStage = stages.find(
    (stage: Row) => stage.stage_type === 'TAC_FINANCIAL_BIDS',
  );
  const tacFinancialComplete = tacFinancialStage?.status === 'COMPLETED';
  const tacFinalReportStage = stages.find(
    (stage: Row) => stage.stage_type === 'TAC_FINAL_REPORT',
  );
  const finalVendorStage = stages.find(
    (stage: Row) => stage.stage_type === 'VENDOR_SELECTION',
  );
  const latestTacFormation = latestRevision(tacFormationSubmissions);
  const tacFormationComplete = projectTacCommittee?.status === 'ACTIVE'
    && latestTacFormation?.status === 'APPROVED';
  const workflowSteps = [
    { badge: 'PRJ', title: 'Project created', status: 'Completed', state: 'complete' },
    {
      badge: 'SS',
      title: 'Form TSC · SS approval',
      status: tscFormationComplete
        ? 'Completed'
        : latestFormation?.status === 'IN_REVIEW'
          ? 'Awaiting SS'
          : latestFormation?.status === 'REJECTED'
            ? 'Action required'
            : 'Current step',
      state: tscFormationComplete
        ? 'complete'
        : latestFormation?.status === 'IN_REVIEW'
          ? 'waiting'
          : latestFormation?.status === 'REJECTED'
            ? 'action'
            : 'current',
    },
    {
      badge: 'AS',
      title: 'TSC report · AS approval',
      status: !tscFormationComplete
        ? 'Locked · TSC formation must be approved'
        : asReportComplete
          ? 'Completed'
          : latestTscReport?.status === 'NEEDS_RESPONSE' && asReportStep?.status === 'QUERY'
            ? 'Action required'
            : latestTscReport?.status === 'IN_REVIEW'
            ? 'Awaiting AS'
            : ['NEEDS_RESPONSE', 'REJECTED'].includes(latestTscReport?.status)
              ? 'Action required'
              : 'Current step',
      state: !tscFormationComplete
        ? 'locked'
        : asReportComplete
          ? 'complete'
          : latestTscReport?.status === 'NEEDS_RESPONSE' && asReportStep?.status === 'QUERY'
            ? 'action'
          : latestTscReport?.status === 'IN_REVIEW'
            ? 'waiting'
            : ['NEEDS_RESPONSE', 'REJECTED'].includes(latestTscReport?.status)
              ? 'action'
              : 'current',
    },
    {
      badge: 'HQ',
      title: 'TSC report · HQ approval',
      status: !asReportComplete
        ? 'Locked · AS approval required'
        : hqTscReportComplete
          ? 'Completed'
          : latestTscReport?.status === 'NEEDS_RESPONSE' && hqTscReportStep?.status === 'QUERY'
            ? 'Action required'
            : hqTscReportStep?.status === 'PENDING'
              ? 'Awaiting HQ'
              : 'Current step',
      state: !asReportComplete
        ? 'locked'
        : hqTscReportComplete
          ? 'complete'
          : latestTscReport?.status === 'NEEDS_RESPONSE' && hqTscReportStep?.status === 'QUERY'
            ? 'action'
            : hqTscReportStep?.status === 'PENDING'
              ? 'waiting'
              : 'current',
    },
    {
      badge: 'DGS',
      title: 'TSC report · DGS approval',
      status: !hqTscReportComplete
        ? 'Locked · AS and HQ approval required'
        : latestDgsTscReport?.status === 'APPROVED'
          ? 'Completed'
          : latestDgsTscReport?.status === 'IN_REVIEW'
            ? 'Awaiting DGS'
            : ['NEEDS_RESPONSE', 'REJECTED'].includes(latestDgsTscReport?.status)
              ? 'Action required'
              : 'Current step',
      state: !hqTscReportComplete
        ? 'locked'
        : latestDgsTscReport?.status === 'APPROVED'
          ? 'complete'
          : latestDgsTscReport?.status === 'IN_REVIEW'
            ? 'waiting'
            : ['NEEDS_RESPONSE', 'REJECTED'].includes(latestDgsTscReport?.status)
              ? 'action'
              : 'current',
    },
    {
      badge: 'IA',
      title: 'Tender draft · IA Wing approval',
      status: !dgsReportComplete
        ? 'Locked · DGS approval required'
        : tenderDraftComplete
          ? 'Completed'
          : latestTenderDraft?.status === 'IN_REVIEW'
            ? 'Awaiting IA Wing'
            : ['NEEDS_RESPONSE', 'REJECTED'].includes(latestTenderDraft?.status)
              ? 'Action required'
              : 'Current step',
      state: !dgsReportComplete
        ? 'locked'
        : tenderDraftComplete
          ? 'complete'
          : latestTenderDraft?.status === 'IN_REVIEW'
            ? 'waiting'
            : ['NEEDS_RESPONSE', 'REJECTED'].includes(latestTenderDraft?.status)
              ? 'action'
              : 'current',
    },
    {
      badge: 'VND',
      title: 'Select vendors',
      status: !tenderDraftComplete
        ? 'Locked · IA Wing approval required'
        : tecFormationComplete || allSelectedVendorsDispatched
          ? 'Completed'
          : 'Current step',
      state: !tenderDraftComplete
        ? 'locked'
        : tecFormationComplete || allSelectedVendorsDispatched
          ? 'complete'
          : 'current',
    },
    {
      badge: 'SS',
      title: 'Form TEC · SS approval',
      status: !tenderDraftComplete
        ? 'Locked · Tender approval required'
        : !allSelectedVendorsDispatched
          ? 'Locked · Send tender to all selected vendors'
          : tecFormationComplete
            ? 'Completed'
            : projectTecCommittee?.status === 'SUBMITTED'
              ? 'Awaiting SS'
              : ['NEEDS_RESPONSE', 'REJECTED'].includes(latestTecFormation?.status)
                ? 'Action required'
                : 'Current step',
      state: !tenderDraftComplete || !allSelectedVendorsDispatched
        ? 'locked'
        : tecFormationComplete
          ? 'complete'
          : projectTecCommittee?.status === 'SUBMITTED'
            ? 'waiting'
            : ['NEEDS_RESPONSE', 'REJECTED'].includes(latestTecFormation?.status)
              ? 'action'
              : 'current',
    },
    {
      badge: 'TEC',
      title: 'TEC final report · HQ approval',
      status: !tecFormationComplete
        ? 'Locked · TEC formation approval required'
        : tecReportComplete
              ? 'Completed'
              : tecReportStage?.status === 'WAITING_APPROVAL'
                ? 'Awaiting HQ'
                : latestTecReport?.status === 'NEEDS_RESPONSE'
                  ? 'Action required · HQ query'
                  : 'Current step',
      state: !tecFormationComplete
        ? 'locked'
        : tecReportComplete
              ? 'complete'
              : tecReportStage?.status === 'WAITING_APPROVAL'
                ? 'waiting'
                : latestTecReport?.status === 'NEEDS_RESPONSE'
                  ? 'action'
                  : 'current',
    },
    {
      badge: 'ADM',
      title: 'Qualify vendors',
      status: !tecReportComplete
        ? 'Locked · TEC final report required'
        : qualificationComplete
          ? 'Completed'
          : qualificationQuery.isLoading
            ? 'Loading qualification status'
            : qualificationQuery.data?.can_qualify
              ? 'Current step'
              : 'Locked · final report and all technical bids required',
      state: !tecReportComplete
        ? 'locked'
        : qualificationComplete
          ? 'complete'
          : qualificationQuery.isLoading
            ? 'waiting'
            : qualificationQuery.data?.can_qualify
              ? 'current'
              : 'locked',
    },
    {
      badge: 'SS',
      title: 'Form TAC · SS approval',
      status: !qualificationComplete
        ? 'Locked · vendor qualification required'
        : tacFormationComplete
          ? 'Completed'
          : projectTacCommittee?.status === 'SUBMITTED'
            ? 'Awaiting SS'
            : ['NEEDS_RESPONSE', 'REJECTED'].includes(latestTacFormation?.status)
              ? 'Action required'
              : 'Current step',
      state: !qualificationComplete
        ? 'locked'
        : tacFormationComplete
          ? 'complete'
          : projectTacCommittee?.status === 'SUBMITTED'
            ? 'waiting'
            : ['NEEDS_RESPONSE', 'REJECTED'].includes(latestTacFormation?.status)
              ? 'action'
              : 'current',
    },
    {
      badge: 'ADM',
      title: 'Select top vendors · upload financial bids',
      action: admin && tacFormationComplete
        ? tacFinancialComplete ? 'Review submitted financial bids' : 'Open vendor shortlist'
        : undefined,
      status: !tacFormationComplete
        ? 'Locked · TAC formation approval required'
        : tacFinancialComplete
          ? 'Completed'
          : 'Current step',
      state: !tacFormationComplete
        ? 'locked'
        : tacFinancialComplete
          ? 'complete'
          : 'current',
    },
    {
      badge: 'TAC',
      title: 'Final TAC report · chair submission',
      action: tacFinancialComplete
        ? projectTacCommittee?.chair === user.id
          ? tacFinalReportStage?.status === 'COMPLETED'
            ? 'Review final TAC report'
            : 'Upload final TAC report'
          : admin ? 'Review final TAC report' : undefined
        : undefined,
      status: !tacFinancialComplete
        ? 'Locked · Admin financial bids required'
        : tacFinalReportStage?.status === 'COMPLETED'
          ? 'Completed'
          : 'Awaiting TAC chair',
      state: !tacFinancialComplete
        ? 'locked'
        : tacFinalReportStage?.status === 'COMPLETED'
          ? 'complete'
          : 'current',
    },
    {
      badge: 'ADM',
      title: 'Select final vendor',
      action: admin && tacFinalReportStage?.status === 'COMPLETED'
        ? finalVendorStage?.status === 'COMPLETED' ? 'Review final vendor' : 'Select final vendor'
        : undefined,
      status: tacFinalReportStage?.status !== 'COMPLETED'
        ? 'Locked · TAC final report required'
        : finalVendorStage?.status === 'COMPLETED'
          ? 'Completed'
          : 'Current step',
      state: tacFinalReportStage?.status !== 'COMPLETED'
        ? 'locked'
        : finalVendorStage?.status === 'COMPLETED'
          ? 'complete'
          : 'current',
    },
  ];
  async function submitForm(event: FormEvent<HTMLFormElement>, url: string, multipart = false) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const data = multipart ? values : Object.fromEntries(values.entries());
    await action.mutateAsync({ url, data });
    form.reset();
  }

  async function submitTscReportResponse(
    event: FormEvent<HTMLFormElement>,
    submissionId: string,
  ) {
    try {
      await submitForm(event, '/workflow/submissions/', true);
      setRespondingTscReportId(null);
    } catch {
      setRespondingTscReportId(submissionId);
    }
  }

  async function submitTenderDraft(event: FormEvent<HTMLFormElement>) {
    try {
      await submitForm(event, '/workflow/submissions/', true);
      setTenderSupersedesId('');
    } catch {
      // The shared mutation handler displays the API error.
    }
  }

  return (
    <div id={projectScoped ? 'project-workflow' : undefined} className={projectScoped ? 'project-workflow' : 'content'}>
      {!projectScoped && <div className="heading">
        <div>
          <h1>Procurement workflow</h1>
          <div className="muted">Stage schedule, assigned work, approvals, and activity.</div>
        </div>
      </div>}
      {projectScoped && (
        <div className="heading" style={{ justifyContent: 'space-between', gap: 12 }}>
          <div>
            <h2>Project workflow</h2>
            <div className="muted">Stages, actions, submissions, and complete approval history for this project.</div>
          </div>
        </div>
      )}
      {error && <div role="alert" style={{ color: '#b42318', marginBottom: 14 }}>{error}</div>}
      {notice && <div role="status" style={{ color: '#067647', marginBottom: 14 }}>{notice}</div>}
      {admin ? (
        <div className="cards">
          <div className="card"><div className="card-label">Scheduled stages</div><div className="card-value">{stages.length}</div></div>
          <div className="card"><div className="card-label">Pending approvals</div><div className="card-value">{(dashboard.data?.pending_approvals || []).filter((item: Row) => !projectId || item.project_id === projectId).length}</div></div>
          <div className="card"><div className="card-label">Overdue stages</div><div className="card-value">{stages.filter((stage: Row) => stage.overdue).length}</div></div>
        </div>
      ) : null}

      {projectScoped && (
        <section className="panel workflow-sequence">
          <div className="panel-head">
            <div>
              <b>Procurement sequence</b>
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                Each step unlocks only after the previous approval is complete. Completed steps remain in the submission and approval trail below.
              </div>
            </div>
          </div>
          {committeesQuery.isLoading || submissionsQuery.isLoading ? (
            <div className="workflow-panel-content">Loading project progress…</div>
          ) : (
            <ol className="workflow-sequence-list">
              {workflowSteps.map(step => (
                <li className="workflow-sequence-item" data-state={step.state} key={step.title}>
                  <span className="workflow-sequence-number">{step.badge}</span>
                  <span className="workflow-sequence-copy">
                    <b>{step.title}</b>
                    <small>{step.status}</small>
                    {'action' in step && step.action && (
                      <a
                        href={step.title === 'Final TAC report · chair submission'
                          ? '#tac-final-report-panel'
                          : step.title === 'Select final vendor'
                            ? '#tac-final-vendor-panel'
                          : '#tac-financial-bids-panel'}
                        style={{ display: 'inline-block', marginTop: 4, fontWeight: 600 }}
                      >
                        {step.action}
                      </a>
                    )}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </section>
      )}

      {projectScoped && (admin || (
        projectTacCommittee?.status === 'ACTIVE'
        && isCommitteeMember(projectTacCommittee)
      )) && (
        <ProjectTacWorkspace
          projectId={projectId!}
          userId={user.id}
          admin={admin}
          committee={projectTacCommittee || { committee_name: 'Tender Acceptance Committee' }}
          tacActive={projectTacCommittee?.status === 'ACTIVE'}
          isMember={projectTacCommittee ? isCommitteeMember(projectTacCommittee) : false}
          tacFinancialComplete={tacFinancialComplete}
        />
      )}

      <ApprovalInbox user={user} projectId={projectId} />

      <section className="panel">
        <div className="panel-head"><b>Submission and approval trail</b></div>
        {submissionsQuery.isError ? <div className="empty">Could not load submission history.</div> :
          <table><thead><tr><th>SUBMISSION</th><th>REVISION</th><th>STATUS</th><th>FILE</th><th>APPROVAL EVENTS</th></tr></thead>
            <tbody>{submissions.map((submission: Row) => {
              const events = (submission.approval_requests || []).flatMap((request: Row) => request.events || []);
              return <tr key={submission.id}>
                <td>
                  {submissionTitleLabel(submission)}
                  <div className="muted">{workflowTypeLabel(submission.submission_type)}</div>
                  {submission.submission_type === 'TENDER_DRAFT' && (
                    <div className="muted" style={{ marginTop: 6 }}>
                      Vendor dispatch: {dateLabel(submission.expected_vendor_dispatch_date)}
                      {' · '}Bid receipt: {dateLabel(submission.expected_bid_receipt_date)}
                      {' · '}Product arrival: {dateLabel(submission.expected_product_arrival_date)}
                    </div>
                  )}
                </td>
                <td>{submission.revision}</td>
                <td><span className="status">{submission.status}</span></td>
                <td>{submission.file_url && <button className="icon-button" onClick={() =>
                  downloadFile(submission.file_url, `${submission.title}.pdf`)
                }>Open PDF</button>}</td>
                <td>{events.length ? events.map((item: Row) => (
                  <div key={item.id} className="muted" style={{ marginBottom: 5 }}>
                    <b>{item.actor_name}</b> · {item.action} · {new Date(item.created_at).toLocaleString()}
                    {item.comment && <div>{item.comment}</div>}
                  </div>
                )) : 'No approval events yet.'}</td>
              </tr>;
            })}</tbody>
          </table>}
        {!submissions.length && <div className="empty">No submissions yet.</div>}
      </section>

      <section className="panel">
        <div className="panel-head"><b>Committee formation</b></div>
        <table><thead><tr><th>PROJECT</th><th>COMMITTEE</th><th>CHAIR</th><th>STATUS</th><th>ACTION</th></tr></thead>
          <tbody>{committees.map((committee: Row) => (
            <tr key={committee.id}>
              <td>{committee.project_code}</td>
              <td>{committee.committee_type} · {committee.committee_name}</td>
              <td>{committee.chair_name || 'Not set'}</td>
              <td><span className="status">{committee.status}</span></td>
              <td>{admin && committee.status === 'DRAFT' &&
                <button className="icon-button" disabled={action.isPending} onClick={() =>
                  action.mutate({ url: `/workflow/committees/${committee.id}/submit-formation/`, data: {} })
                }>Submit for approval</button>}</td>
            </tr>
          ))}</tbody>
        </table>
        {!committees.length && <div className="empty">No committees have been formed.</div>}
      </section>

      <section className="panel">
        <div className="panel-head"><b>Queries awaiting my response</b></div>
        {submissionsQuery.isError ? <div className="empty">Could not load submissions.</div> :
          <table><thead><tr><th>SUBMISSION</th><th>TYPE</th><th>REVISION</th><th>QUERY</th><th>ACTION</th></tr></thead>
            <tbody>{submissions.filter((submission: Row) => submission.status === 'NEEDS_RESPONSE').map((submission: Row) => {
              const approval = submission.approval_requests?.[submission.approval_requests.length - 1];
              const query = approval?.events?.filter((item: Row) => item.action === 'QUERY').slice(-1)[0];
              const committee = projectCommittees.find((item: Row) => item.id === submission.committee);
              return (
                <Fragment key={submission.id}>
                  <tr>
                    <td>{submissionTitleLabel(submission)}</td><td>{workflowTypeLabel(submission.submission_type)}</td><td>{submission.revision}</td>
                    <td>{query?.comment || 'Review the approval history'}</td>
                    <td>
                      {admin && ['TSC_FORMATION', 'TEC_FORMATION', 'TAC_FORMATION'].includes(submission.submission_type) ? (
                        <button className="icon-button" onClick={() => {
                          setError('');
                          setEditingFormationSubmissionId(
                            editingFormationSubmissionId === submission.id ? null : submission.id,
                          );
                        }}>
                          {editingFormationSubmissionId === submission.id
                            ? 'Close committee editor'
                            : `Edit ${submission.submission_type === 'TEC_FORMATION'
                              ? 'TEC'
                              : submission.submission_type === 'TAC_FORMATION' ? 'TAC' : 'TSC'} and resend for approval`}
                        </button>
                      ) : ['TSC_REPORT', 'TSC_REPORT_LEVEL3'].includes(submission.submission_type) ? (
                        submission.submitted_by === user.id ? (
                          <button
                            className="icon-button"
                            onClick={() => setRespondingTscReportId(
                              respondingTscReportId === submission.id ? null : submission.id,
                            )}
                          >
                            {respondingTscReportId === submission.id
                              ? 'Cancel report revision'
                              : `Respond and upload revised ${submission.submission_type === 'TSC_REPORT_LEVEL3' ? 'DGS' : 'AS'} report`}
                          </button>
                        ) : 'Awaiting the TSC chair’s revised report'
                      ) : submission.submission_type === 'TEC_REPORT' ? (
                        submission.submitted_by === user.id ? (
                          <button
                            className="icon-button"
                            onClick={() => document.getElementById('tec-report-workspace')?.scrollIntoView({ behavior: 'smooth' })}
                          >
                            Respond to HQ in the TEC report workspace
                          </button>
                        ) : 'Awaiting the TEC chair’s revised report'
                      ) : admin && submission.submission_type === 'TENDER_DRAFT' ? (
                        <button className="icon-button" onClick={() => {
                          setTenderSupersedesId(submission.id);
                          document.getElementById('tender-draft-form')?.scrollIntoView({ behavior: 'smooth' });
                        }}>
                          Respond with revised tender PDF
                        </button>
                      ) : (admin || submission.submitted_by === user.id) ? (
                        <button className="icon-button" onClick={async () => {
                          const comment = window.prompt('Enter your response to the query:');
                          if (comment?.trim()) {
                            try {
                              await action.mutateAsync({
                                url: `/workflow/submissions/${submission.id}/respond/`,
                                data: { comment },
                              });
                            } catch {
                              // The shared mutation handler displays the API error.
                            }
                          }
                        }}>Respond</button>
                      ) : 'Awaiting the submitter’s response'}
                    </td>
                  </tr>
                  {['TSC_REPORT', 'TSC_REPORT_LEVEL3'].includes(submission.submission_type)
                    && submission.submitted_by === user.id
                    && respondingTscReportId === submission.id && (
                      <tr>
                        <td colSpan={5} style={{ background: '#f8fafc' }}>
                          <form
                            onSubmit={event => submitTscReportResponse(event, submission.id)}
                            style={{ padding: 16, display: 'grid', gap: 10, maxWidth: 620 }}
                          >
                            <b>
                              Respond to {submission.submission_type === 'TSC_REPORT_LEVEL3' ? 'DGS' : 'AS'}
                              {' '}and resubmit the TSC report
                            </b>
                            <div className="muted">
                              Your response and revised PDF will be sent together as the next report revision.
                            </div>
                            <input
                              type="hidden"
                              name="submission_type"
                              value={submission.submission_type}
                            />
                            <input type="hidden" name="committee" value={submission.committee} />
                            {submission.source_report && (
                              <input type="hidden" name="source_report" value={submission.source_report} />
                            )}
                            <input type="hidden" name="title" value={submission.title || 'TSC Report'} />
                            <label className="muted">
                              Response to {submission.submission_type === 'TSC_REPORT_LEVEL3' ? 'DGS' : 'AS'} query
                              <textarea name="comments" rows={4} required placeholder="Explain how the query was addressed." />
                            </label>
                            <label className="muted">
                              Revised TSC report PDF
                              <input name="file" type="file" accept="application/pdf,.pdf" required />
                            </label>
                            <div style={{ display: 'flex', gap: 8 }}>
                              <button className="button primary" disabled={action.isPending}>
                                {action.isPending
                                  ? 'Sending revised report…'
                                  : `Send revised report to ${submission.submission_type === 'TSC_REPORT_LEVEL3' ? 'DGS' : 'AS'}`}
                              </button>
                              <button
                                type="button"
                                className="icon-button"
                                disabled={action.isPending}
                                onClick={() => setRespondingTscReportId(null)}
                              >
                                Cancel
                              </button>
                            </div>
                          </form>
                        </td>
                      </tr>
                    )}
                  {admin && ['TSC_FORMATION', 'TEC_FORMATION', 'TAC_FORMATION'].includes(submission.submission_type)
                    && editingFormationSubmissionId === submission.id && (
                      <tr>
                        <td colSpan={5} style={{ background: '#f8fafc' }}>
                          {committee ? (
                            <CommitteeQueryResponseForm
                              committee={committee}
                              committeeType={
                                submission.submission_type === 'TEC_FORMATION'
                                  ? 'TEC'
                                  : submission.submission_type === 'TAC_FORMATION' ? 'TAC' : 'TSC'
                              }
                              approverRole="SS"
                              employees={employees}
                              submission={submission}
                              busy={action.isPending}
                              onCancel={() => setEditingFormationSubmissionId(null)}
                              onSubmit={async values => {
                                try {
                                  await action.mutateAsync({
                                    url: `/workflow/submissions/${submission.id}/respond/`,
                                    data: values,
                                  });
                                  setEditingFormationSubmissionId(null);
                                } catch {
                                  // The shared mutation handler displays the API error.
                                }
                              }}
                              setError={setError}
                            />
                          ) : <div role="alert" className="workflow-panel-content">Could not load the TSC details for editing.</div>}
                        </td>
                      </tr>
                    )}
                </Fragment>
              );
            })}</tbody>
          </table>}
        {!submissions.some((submission: Row) => submission.status === 'NEEDS_RESPONSE') &&
          <div className="empty">No queries are awaiting your response.</div>}
      </section>

      {admin && <section className="panel">
        <div className="panel-head"><b>Project stage timeline</b></div>
        {stagesQuery.isError ? <div className="empty">Could not load stages.</div> :
          <table><thead><tr><th>PROJECT</th><th>STAGE / MILESTONE</th><th>STATUS</th><th>PLANNED START</th><th>EXPECTED DEADLINE</th><th>COMPLETED</th><th>DETAILS</th></tr></thead>
            <tbody>{timelineRows.map((row: Row) => (
              <tr key={row.timeline_key}>
                <td>{row.project_code}</td>
                <td>{row.is_milestone ? row.stage_type : workflowTypeLabel(row.stage_type)}</td>
                <td>
                  <span
                    className="status"
                    style={row.status === 'DELAYED'
                      ? { background: '#fef3f2', color: '#b42318' }
                      : row.status === 'COMPLETED_LATE'
                        ? { background: '#fff7ed', color: '#c2410c' }
                        : undefined}
                  >
                    {timelineStatusLabel(row.status)}
                  </span>
                </td>
                <td>{row.is_milestone ? '—' : dateLabel(row.planned_start)}</td>
                <td>{dateLabel(row.due_date)}</td>
                <td>{row.completed_at ? new Date(row.completed_at).toLocaleDateString() : '—'}</td>
                <td>{row.timeline_details || '—'}</td>
              </tr>
            ))}</tbody>
          </table>}
        {!stages.length && !stagesQuery.isLoading && <div className="empty">No stages have been scheduled.</div>}
      </section>}

      {tscFormationComplete && tscChairCommittee
        && (!latestTscReport || latestTscReport.status === 'REJECTED') && (
        <section className="panel">
          <div className="panel-head"><b>Submit TSC report to AS</b></div>
          <form onSubmit={event => submitForm(event, '/workflow/submissions/', true)} style={{ padding: 16, display: 'grid', gap: 10, maxWidth: 620 }}>
            <input type="hidden" name="submission_type" value="TSC_REPORT" />
            <input type="hidden" name="committee" value={tscChairCommittee.id} />
            <input type="hidden" name="title" value="TSC Report" />
            <label className="muted">TSC report PDF<input name="file" type="file" accept="application/pdf,.pdf" required /></label>
            <label className="muted">Comment <span>(optional)</span><textarea name="comments" rows={3} placeholder="Add a note for AS, if needed." /></label>
            <button className="button primary" disabled={action.isPending}>Send report to AS</button>
          </form>
        </section>
      )}

      {tscFormationComplete && projectTscCommittee && canSubmitDgsReport
        && latestTscReport?.status === 'APPROVED'
        && (!latestDgsTscReport || latestDgsTscReport.status === 'REJECTED')
        && (
          <section className="panel">
            <div className="panel-head">
              <div>
                <b>{latestDgsTscReport ? 'Resubmit TSC report to DGS' : 'Send approved TSC report to DGS'}</b>
                <div className="muted">
                  AS and HQ approved revision {latestTscReport.revision}. DGS review starts only after both approvals.
                </div>
              </div>
            </div>
            <form
              onSubmit={event => submitForm(event, '/workflow/submissions/', true)}
              style={{ padding: 16, display: 'grid', gap: 10, maxWidth: 620 }}
            >
              <input type="hidden" name="submission_type" value="TSC_REPORT_LEVEL3" />
              <input type="hidden" name="committee" value={projectTscCommittee.id} />
              <input type="hidden" name="source_report" value={latestTscReport.id} />
              <input type="hidden" name="title" value="TSC Report — DGS Review" />
              {latestDgsTscReport?.status === 'REJECTED' && (
                <>
                  <input type="hidden" name="supersedes" value={latestDgsTscReport.id} />
                  <label className="muted">
                    Revised TSC report PDF
                    <input name="file" type="file" accept="application/pdf,.pdf" required />
                  </label>
                  <label className="muted">
                    Comment <span>(optional)</span>
                    <textarea name="comments" rows={3} placeholder="Add a note for DGS, if needed." />
                  </label>
                </>
              )}
              {!latestDgsTscReport && (
                <label className="muted">
                  Comment <span>(optional)</span>
                  <textarea name="comments" rows={3} placeholder="Add a note for DGS, if needed." />
                </label>
              )}
              <button className="button primary" disabled={action.isPending}>
                {latestDgsTscReport ? 'Resubmit report to DGS' : 'Send approved report to DGS'}
              </button>
            </form>
          </section>
        )}

      {admin && (
        <>
          {(projectScoped || tenderDraftStages.length > 0) && (
            <section className="panel">
              <div className="panel-head">
                <div>
                  <b>Tender draft</b>
                  <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                    This step opens after DGS approves the latest TSC report.
                  </div>
                </div>
                {tenderDraftComplete && <span className="status">APPROVED</span>}
              </div>
              {projectScoped && !dgsReportComplete ? (
                <div className="workflow-panel-content">
                  Tender submission is locked until DGS approves the TSC report after AS and HQ approval.
                </div>
              ) : tenderDraftComplete ? (
                <div className="workflow-panel-content">
                  The latest tender draft is approved. Tender submission is complete; vendor selection is now enabled.
                </div>
              ) : projectScoped && latestTenderDraft?.status === 'IN_REVIEW' ? (
                <div className="workflow-panel-content">
                  Tender draft revision {latestTenderDraft.revision} is awaiting IA Wing. Submission is locked while approval is pending.
                </div>
              ) : (
                <form key={tenderSupersedesId} id="tender-draft-form" className="workflow-panel-content" onSubmit={submitTenderDraft} style={{ display: 'grid', gap: 10, maxWidth: 620 }}>
                  <b>Admin: submit tender draft</b>
                  <small className="muted">
                    Set expected vendor dispatch, bid receipt, and product arrival dates before sending the PDF to IA Wing.
                    Dispatch and bid receipt progress is tracked in the timeline; product arrival is shown for reference.
                  </small>
                  <select
                    name="stage"
                    required
                    defaultValue={projectScoped ? tenderDraftStages[0]?.id || '' : ''}
                  >
                    <option value="" disabled>Tender draft stage</option>
                    {tenderDraftStages.map((stage: Row) => (
                      <option key={stage.id} value={stage.id}>
                        {stage.project_code} · Tender draft
                      </option>
                    ))}
                  </select>
                  <input type="hidden" name="submission_type" value="TENDER_DRAFT" />
                  <input name="title" defaultValue="Tender draft" required />
                  <label className="muted">
                    Expected date tender will be sent to vendors
                    <input
                      name="expected_vendor_dispatch_date"
                      type="date"
                      required
                      defaultValue={selectedTenderSupersedes?.expected_vendor_dispatch_date || ''}
                    />
                  </label>
                  <label className="muted">
                    Expected bid receipt deadline
                    <input
                      name="expected_bid_receipt_date"
                      type="date"
                      required
                      defaultValue={selectedTenderSupersedes?.expected_bid_receipt_date || ''}
                    />
                  </label>
                  <label className="muted">
                    Expected product arrival date
                    <input
                      name="expected_product_arrival_date"
                      type="date"
                      required
                      defaultValue={selectedTenderSupersedes?.expected_product_arrival_date || ''}
                    />
                  </label>
                  <label className="muted">
                    Draft tender PDF
                    <input name="file" type="file" accept="application/pdf,.pdf" required />
                  </label>
                  <label className="muted">
                    Comment <span>{selectedTenderSupersedes?.status === 'NEEDS_RESPONSE' ? '(required for query response)' : '(optional)'}</span>
                    <textarea
                      name="comments"
                      rows={3}
                      required={selectedTenderSupersedes?.status === 'NEEDS_RESPONSE'}
                      placeholder="Add a note for IA Wing, or respond to the query."
                    />
                  </label>
                  <select
                    name="supersedes"
                    value={tenderSupersedesId}
                    onChange={event => setTenderSupersedesId(event.target.value)}
                  >
                    <option value="">New submission</option>
                    {revisableTenderDrafts.map((submission: Row) => (
                      <option key={submission.id} value={submission.id}>
                        {submission.status === 'NEEDS_RESPONSE' ? 'Query response' : 'Resubmission'}
                        {' · '}revision {submission.revision}
                      </option>
                    ))}
                  </select>
                  <button className="button primary" disabled={action.isPending || !tenderDraftStages.length}>
                    {tenderSupersedesId ? 'Resubmit tender draft' : 'Send tender draft to IA Wing'}
                  </button>
                  {!tenderDraftStages.length && (
                    <small className="muted">The tender stage will be created after DGS approves the TSC report.</small>
                  )}
                </form>
              )}
            </section>
          )}
          {projectScoped && tenderDraftComplete && (
            <ProjectVendorSelection
              projectId={projectId!}
              userId={user.id}
              enabled={admin}
              committees={projectCommittees}
              employees={employees}
            />
          )}
          {projectScoped && admin && (
            <ProjectTacFormation
              projectId={projectId!}
              userId={user.id}
              qualificationComplete={Boolean(qualificationComplete)}
              committee={projectTacCommittee}
              employees={employees}
            />
          )}
        </>
      )}
      {projectScoped && projectTecCommittee?.status === 'ACTIVE' && (
        <ProjectTecWorkspace
          projectId={projectId!}
          userId={user.id}
          admin={admin}
          committee={projectTecCommittee}
          finalReportSubmission={latestTecReport || undefined}
          reportStage={tecReportStage || undefined}
          isMember={myTecCommittees.some(
            (committee: Row) => committee.id === projectTecCommittee.id,
          )}
        />
      )}
      {(!admin || myTscCommittees.length > 0) && (
        <>
          {tscFormationComplete && myTscCommittees.length > 0 && (
            <section className="panel">
              <div className="panel-head">
                <div>
                  <b>TSC report versions</b>
                  <div className="muted">Upload working report versions and access documents shared by other TSC members. The chair submits a final version separately for approval.</div>
                </div>
              </div>
              <form onSubmit={event => submitForm(event, '/workflow/tsc-documents/', true)} style={{ padding: 16, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                <select name="committee" required defaultValue={myTscCommittees.length === 1 ? myTscCommittees[0].id : ''}>
                  <option value="" disabled>TSC committee</option>
                  {myTscCommittees.map((committee: Row) => <option key={committee.id} value={committee.id}>{committee.project_code} · {committee.committee_name}</option>)}
                </select>
                <input name="file" type="file" accept="application/pdf,.pdf" required />
                <button className="button primary" disabled={action.isPending}>Share PDF with TSC</button>
              </form>
              {tscDocumentsQuery.isError ? <div role="alert" className="empty">Could not load TSC documents.</div> :
                <table><thead><tr><th>VERSION</th><th>FILE</th><th>UPLOADED BY</th><th>UPLOADED</th><th>ACTION</th></tr></thead>
                  <tbody>{rowsFrom(tscDocumentsQuery.data)
                    .filter((document: Row) => myTscCommittees.some((committee: Row) => committee.id === document.committee))
                    .map((document: Row) => (
                      <tr key={document.id}>
                        <td>Version {document.version}</td>
                        <td>{document.file_name}</td>
                        <td>{document.uploaded_by_name}</td>
                        <td>{new Date(document.uploaded_at).toLocaleString()}</td>
                        <td><button className="icon-button" onClick={() => downloadFile(document.file_url, document.file_name)}>Download PDF</button></td>
                      </tr>
                    ))}</tbody>
                </table>}
              {!tscDocumentsQuery.isLoading && !tscDocumentsQuery.isError
                && !rowsFrom(tscDocumentsQuery.data).some((document: Row) => myTscCommittees.some((committee: Row) => committee.id === document.committee))
                && <div className="empty">No shared TSC documents yet.</div>}
            </section>
          )}
        </>
      )}
    </div>
  );
}

function ProjectTecWorkspace({
  projectId,
  userId,
  admin,
  committee,
  finalReportSubmission,
  reportStage,
  isMember,
}: {
  projectId: string;
  userId: string;
  admin: boolean;
  committee: Row;
  finalReportSubmission?: Row;
  reportStage?: Row;
  isMember: boolean;
}) {
  const queryClient = useQueryClient();
  const selectionsQuery = useQuery({
    queryKey: ['project-vendors', projectId, userId],
    queryFn: async () => (await api.get(`/projects/${projectId}/vendors/`)).data,
    enabled: admin || isMember,
  });
  const bidsQuery = useQuery({
    queryKey: ['project-bids', projectId, userId],
    queryFn: () => fetchAll(`/workflow/bids/?project=${projectId}`),
    enabled: admin || isMember,
  });
  const documentsQuery = useQuery({
    queryKey: ['tec-documents', projectId, userId],
    queryFn: () => fetchAll(`/workflow/tec-documents/?project=${projectId}`),
    enabled: admin || isMember,
  });
  const qualificationQuery = useQuery({
    queryKey: ['qualified-vendors', projectId],
    queryFn: async () => (await api.get(`/projects/${projectId}/qualified-vendors/`)).data,
    enabled: admin,
  });
  const tendersQuery = useQuery({
    queryKey: ['project-tender', projectId, userId],
    queryFn: () => fetchAll(`/workflow/tenders/?project=${projectId}`),
    enabled: admin,
  });
  const uploadTechnicalBid = useMutation({
    mutationFn: (data: FormData) => api.post('/workflow/bids/receive/', data),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['project-bids', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['project-vendors', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-stages'] }),
        queryClient.invalidateQueries({ queryKey: ['activities', projectId] }),
      ]);
    },
  });
  const uploadTecDocument = useMutation({
    mutationFn: (data: FormData) => api.post('/workflow/tec-documents/', data),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['tec-documents', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-stages'] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['activities', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['notifications'] }),
      ]);
    },
  });
  const submitFinalReport = useMutation({
    mutationFn: (data: FormData) => api.post('/workflow/submissions/', data),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workflow-submissions', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-stages'] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['tec-documents', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['activities', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['notifications'] }),
      ]);
    },
  });
  const qualifyVendors = useMutation({
    mutationFn: (vendorIds: string[]) =>
      api.post(`/projects/${projectId}/qualified-vendors/`, { vendor_ids: vendorIds }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['qualified-vendors', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-stages'] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['activities', projectId] }),
      ]);
    },
  });
  const [qualifiedVendorIds, setQualifiedVendorIds] = useState<string[]>([]);
  const [qualificationNotice, setQualificationNotice] = useState('');
  useEffect(() => {
    if (qualificationQuery.data) {
      setQualifiedVendorIds(
        qualificationQuery.data.vendors
          .filter((vendor: Row) => vendor.qualification_status === 'QUALIFIED')
          .map((vendor: Row) => vendor.vendor_id),
      );
    }
  }, [qualificationQuery.data]);

  const vendors: Row[] = selectionsQuery.data?.vendors || [];
  const bids: Row[] = rowsFrom(bidsQuery.data);
  const documents: Row[] = rowsFrom(documentsQuery.data);
  const tender = rowsFrom(tendersQuery.data)[0];
  const chair = committee.chair === userId;
  const finalReports = documents.filter(
    (document: Row) => document.document_type === 'FINAL',
  );
  const workingReports = documents.filter(
    (document: Row) => document.document_type === 'WORKING',
  );
  const uploadedTechnicalVendorIds = new Set(
    bids
      .filter((bid: Row) => bid.documents?.some(
        (document: Row) => document.document_type === 'TECHNICAL',
      ))
      .map((bid: Row) => bid.vendor),
  );
  const allTechnicalBidsUploaded = vendors.length > 0
    && vendors.every((vendor: Row) => uploadedTechnicalVendorIds.has(vendor.vendor_id));

  function submitTechnicalBid(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    data.set('tender', tender.id);
    uploadTechnicalBid.mutate(data, {
      onSuccess: () => form.reset(),
    });
  }

  function submitReport(event: FormEvent<HTMLFormElement>, type: 'WORKING' | 'FINAL') {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    if (type === 'FINAL') {
      if (reportStage?.id) data.set('stage', reportStage.id);
      data.set('submission_type', 'TEC_REPORT');
      data.set('committee', committee.id);
      data.set('title', 'TEC Final Report');
      data.set('comments', String(data.get('comments') || ''));
      if (finalReportSubmission?.status === 'NEEDS_RESPONSE') {
        data.set('supersedes', finalReportSubmission.id);
      }
      submitFinalReport.mutate(data, {
        onSuccess: () => form.reset(),
      });
      return;
    }
    data.set('committee', committee.id);
    data.set('document_type', type);
    uploadTecDocument.mutate(data, {
      onSuccess: () => form.reset(),
    });
  }

  function submitQualification(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQualificationNotice('');
    qualifyVendors.mutate(qualifiedVendorIds, {
      onSuccess: () => setQualificationNotice('Qualified vendors saved. The decision is recorded in the project history.'),
    });
  }

  return (
    <section className="panel" id="tec-report-workspace">
      <div className="panel-head">
        <div>
          <b>Technical evaluation · {committee.committee_name}</b>
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
            Technical bid PDFs are available to active TEC members. Financial bids are not exposed in TEC review.
          </div>
        </div>
      </div>
      {selectionsQuery.isLoading || bidsQuery.isLoading ? (
        <div className="empty">Loading selected vendors and technical bids…</div>
      ) : selectionsQuery.isError || bidsQuery.isError ? (
        <div role="alert" className="workflow-alert error">Could not load the TEC bid workspace.</div>
      ) : (
        <div className="workflow-panel-content">
          {admin && (
            <section>
              <b>Upload vendors’ technical bids</b>
              {tendersQuery.isError && (
                <div role="alert" className="workflow-alert error">Could not load the approved tender.</div>
              )}
              {!vendors.length ? (
                <div className="empty">There are no selected vendors for this project.</div>
              ) : (
                <div style={{ display: 'grid', gap: 12, marginTop: 10 }}>
                  {vendors.map((vendor: Row) => {
                    const bid = bids.find((item: Row) => item.vendor === vendor.vendor_id);
                    const technicalDocument = bid?.documents?.find(
                      (document: Row) => document.document_type === 'TECHNICAL',
                    );
                    const dispatched = ['TENDER_SENT', 'BID_RECEIVED'].includes(
                      vendor.participation_status,
                    );
                    return (
                      <article className="card" key={vendor.vendor_id}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                          <div>
                            <b>{vendor.vendor_name}</b>
                            <div className="muted">{vendor.participation_status.replaceAll('_', ' ')}</div>
                            {technicalDocument && (
                              <button
                                type="button"
                                className="icon-button"
                                onClick={() => downloadFile(technicalDocument.file_url, `${vendor.vendor_name}-technical-bid.pdf`)}
                              >
                                Download technical bid · Version {technicalDocument.version}
                              </button>
                            )}
                          </div>
                          {!technicalDocument && dispatched && tender?.id && (
                            <form onSubmit={submitTechnicalBid} style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                              <input type="hidden" name="vendor" value={vendor.vendor_id} />
                              <input
                                name="technical_file"
                                type="file"
                                accept="application/pdf,.pdf"
                                aria-label={`Technical bid PDF for ${vendor.vendor_name}`}
                                required
                              />
                              <button className="button primary" disabled={uploadTechnicalBid.isPending}>
                                {uploadTechnicalBid.isPending ? 'Uploading…' : 'Upload technical bid'}
                              </button>
                            </form>
                          )}
                          {!dispatched && (
                            <span className="muted">Record tender dispatch before uploading a bid.</span>
                          )}
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}
              {uploadTechnicalBid.isError && (
                <div role="alert" className="workflow-alert error">
                  {messageFromError(uploadTechnicalBid.error)}
                </div>
              )}
            </section>
          )}

          <section style={{ marginTop: 24 }}>
            <b>Technical bid documents</b>
            {bids.length ? (
              <table>
                <thead><tr><th>VENDOR</th><th>RECEIVED</th><th>TECHNICAL BID</th></tr></thead>
                <tbody>
                  {bids.map((bid: Row) => {
                    const technicalDocument = bid.documents?.find(
                      (document: Row) => document.document_type === 'TECHNICAL',
                    );
                    return (
                      <tr key={bid.id}>
                        <td>{bid.vendor_name}</td>
                        <td>{new Date(bid.received_at).toLocaleString()}</td>
                        <td>{technicalDocument ? (
                          <button
                            type="button"
                            className="icon-button"
                            onClick={() => downloadFile(technicalDocument.file_url, `${bid.vendor_name}-technical-bid.pdf`)}
                          >
                            Download PDF · Version {technicalDocument.version}
                          </button>
                        ) : 'Not uploaded'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : <div className="empty">No technical bids have been uploaded yet.</div>}
          </section>

          <section style={{ marginTop: 24 }}>
            <div className="panel-head">
              <div>
                <b>TEC report collaboration</b>
                <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  TEC members can share working report PDFs. Only the TEC chair can submit the final report to Admin.
                </div>
              </div>
            </div>
            {isMember && (
              <form
                onSubmit={event => submitReport(event, 'WORKING')}
                style={{ display: 'flex', gap: 10, flexWrap: 'wrap', margin: '12px 0' }}
              >
                <input name="file" type="file" accept="application/pdf,.pdf" required />
                <button className="button primary" disabled={uploadTecDocument.isPending}>
                  Share working report
                </button>
              </form>
            )}
            {chair && (
              <form
                onSubmit={event => submitReport(event, 'FINAL')}
                style={{ display: 'flex', gap: 10, flexWrap: 'wrap', margin: '12px 0' }}
              >
                <input name="file" type="file" accept="application/pdf,.pdf" required />
                {finalReportSubmission?.status === 'NEEDS_RESPONSE' && (
                  <label className="muted" style={{ flexBasis: '100%' }}>
                    Response to HQ query
                    <textarea
                      name="comments"
                      rows={3}
                      required
                      placeholder="Explain how the query was addressed."
                    />
                  </label>
                )}
                <button
                  className="button primary"
                  disabled={
                    uploadTecDocument.isPending
                    || submitFinalReport.isPending
                    || !allTechnicalBidsUploaded
                  }
                >
                  {finalReportSubmission?.status === 'NEEDS_RESPONSE'
                    ? 'Respond to HQ and upload revised final report'
                    : finalReports.length
                      ? 'Submit revised final TEC report'
                      : 'Submit final TEC report for HQ approval'}
                </button>
                {!allTechnicalBidsUploaded && (
                  <small className="muted">Upload the technical bid for every selected vendor before submitting the final report.</small>
                )}
              </form>
            )}
            {uploadTecDocument.isError && (
              <div role="alert" className="workflow-alert error">
                {messageFromError(uploadTecDocument.error)}
              </div>
            )}
            {submitFinalReport.isError && (
              <div role="alert" className="workflow-alert error">
                {messageFromError(submitFinalReport.error)}
              </div>
            )}
            {documentsQuery.isError ? (
              <div role="alert" className="workflow-alert error">Could not load TEC report documents.</div>
            ) : (
              <>
                {!!finalReports.length && (
                  <div style={{ display: 'grid', gap: 8, marginTop: 12 }}>
                    <b>Final reports available to Admin</b>
                    {finalReports.map((document: Row) => (
                      <article className="card" key={document.id}>
                        <b>{document.file_name} · Version {document.version}</b>
                        <div className="muted">
                          Submitted by {document.uploaded_by_name} · {new Date(document.uploaded_at).toLocaleString()}
                        </div>
                        <button
                          type="button"
                          className="icon-button"
                          onClick={() => downloadFile(document.file_url, document.file_name)}
                        >
                          Download final report
                        </button>
                      </article>
                    ))}
                  </div>
                )}
                {!!workingReports.length && (
                  <div style={{ marginTop: 16 }}>
                    <b>Shared working reports</b>
                    <table>
                      <thead><tr><th>VERSION</th><th>FILE</th><th>UPLOADED BY</th><th>UPLOADED</th><th>ACTION</th></tr></thead>
                      <tbody>
                        {workingReports.map((document: Row) => (
                          <tr key={document.id}>
                            <td>{document.version}</td>
                            <td>{document.file_name}</td>
                            <td>{document.uploaded_by_name}</td>
                            <td>{new Date(document.uploaded_at).toLocaleString()}</td>
                            <td>
                              <button
                                type="button"
                                className="icon-button"
                                onClick={() => downloadFile(document.file_url, document.file_name)}
                              >
                                Download PDF
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {!finalReports.length && !workingReports.length && (
                  <div className="empty">No TEC reports have been shared yet.</div>
                )}
              </>
            )}
          </section>
          {admin && (
            <section className="panel" style={{ marginTop: 24 }}>
              <div className="panel-head">
                <div>
                  <b>Admin · qualify vendors</b>
                  <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                    Mark vendors as technically qualified using the TEC final report.
                  </div>
                </div>
              </div>
              {qualificationQuery.isLoading ? (
                <div className="empty">Loading vendor qualification status…</div>
              ) : qualificationQuery.isError ? (
                <div role="alert" className="workflow-alert error">
                  Could not load vendor qualification status.
                </div>
              ) : qualificationQuery.data?.qualification_complete ? (
                <div className="workflow-panel-content">
                  <div className="muted">Qualification is complete and locked. The decision remains in the project history.</div>
                  <div style={{ display: 'grid', gap: 8, marginTop: 10 }}>
                    {qualificationQuery.data.vendors.map((vendor: Row) => (
                      <article className="card" key={vendor.vendor_id}>
                        <b>{vendor.vendor_name}</b>
                        <div>{vendor.qualification_status.replaceAll('_', ' ')}</div>
                        <small className="muted">
                          Recorded by {vendor.qualification_decided_by || 'Admin'}
                          {vendor.qualification_decided_at
                            ? ` · ${new Date(vendor.qualification_decided_at).toLocaleString()}`
                            : ''}
                        </small>
                      </article>
                    ))}
                  </div>
                  {qualificationNotice && <div className="workflow-alert success">{qualificationNotice}</div>}
                </div>
              ) : !qualificationQuery.data?.can_qualify ? (
                <div className="workflow-panel-content">
                  {qualificationQuery.data?.final_report_received
                    ? 'Upload technical bids for every selected vendor before qualifying vendors.'
                    : 'This step unlocks after the TEC chair submits the final report.'}
                </div>
              ) : (
                <form className="workflow-panel-content" onSubmit={submitQualification}>
                  <div style={{ display: 'grid', gap: 8 }}>
                    {qualificationQuery.data.vendors.map((vendor: Row) => (
                      <label className="card" key={vendor.vendor_id} style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                        <input
                          type="checkbox"
                          checked={qualifiedVendorIds.includes(vendor.vendor_id)}
                          onChange={event => setQualifiedVendorIds(current =>
                            event.target.checked
                              ? [...current, vendor.vendor_id]
                              : current.filter(id => id !== vendor.vendor_id),
                          )}
                        />
                        <span>
                          <b>{vendor.vendor_name}</b>
                          <span className="muted"> · {vendor.qualification_status.replaceAll('_', ' ')}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                  <button
                    className="button primary"
                    style={{ marginTop: 12 }}
                    disabled={qualifyVendors.isPending || qualifiedVendorIds.length === 0}
                  >
                    {qualifyVendors.isPending ? 'Saving…' : 'Save qualified vendors'}
                  </button>
                  {qualifyVendors.isError && (
                    <div role="alert" className="workflow-alert error">
                      {messageFromError(qualifyVendors.error)}
                    </div>
                  )}
                  {qualificationNotice && <div className="workflow-alert success">{qualificationNotice}</div>}
                </form>
              )}
            </section>
          )}
        </div>
      )}
    </section>
  );
}

function ProjectVendorSelection({
  projectId,
  userId,
  enabled,
  committees,
  employees,
}: {
  projectId: string;
  userId: string;
  enabled: boolean;
  committees: Row[];
  employees: Row[];
}) {
  const queryClient = useQueryClient();
  const [requirement, setRequirement] = useState('');
  const [matches, setMatches] = useState<Row[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [tecError, setTecError] = useState('');
  const selectionsQuery = useQuery({
    queryKey: ['project-vendors', projectId, userId],
    queryFn: async () => (await api.get(`/projects/${projectId}/vendors/`)).data,
    enabled,
  });
  const selections: Row[] = selectionsQuery.data?.vendors || [];
  const tenderDraftApproved = Boolean(selectionsQuery.data?.tender_draft_approved);
  const tec = committees.find(
    (committee: Row) => committee.committee_type === 'TEC' && committee.status !== 'REJECTED',
  );
  const createTec = useMutation({
    mutationFn: (data: FormData) => api.post('/workflow/committees/', data),
    onSuccess: async () => {
      setTecError('');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workflow-committees', userId] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-submissions', userId] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-dashboard', userId] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-stages', userId] }),
        queryClient.invalidateQueries({ queryKey: ['project-vendors', projectId, userId] }),
      ]);
    },
    onError: (error: any) => setTecError(messageFromError(error)),
  });
  const tenderQuery = useQuery({
    queryKey: ['project-tender', projectId, userId],
    queryFn: () => fetchAll(`/workflow/tenders/?project=${projectId}`),
    enabled: enabled && tenderDraftApproved,
  });
  const search = useMutation({
    mutationFn: async () => (await api.post('/vendors/match/', { query: requirement.trim() })).data,
    onSuccess: results => {
      setMatches(results);
      setSelectedIds([]);
    },
  });
  const saveSelections = useMutation({
    mutationFn: async () => api.post(`/projects/${projectId}/vendors/`, { vendor_ids: selectedIds }),
    onSuccess: async () => {
      setSelectedIds([]);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['project-vendors', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-stages'] }),
      ]);
    },
  });
  const removeSelection = useMutation({
    mutationFn: async (vendorId: string) => api.delete(`/projects/${projectId}/vendors/`, {
      data: { vendor_id: vendorId },
    }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['project-vendors', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-stages'] }),
      ]);
    },
  });
  const recordDispatch = useMutation({
    mutationFn: async (vendorId: string) => {
      let tender = rowsFrom(tenderQuery.data)[0];
      if (!tender) {
        tender = (await api.post('/workflow/tenders/ensure/', { project: projectId })).data;
      }
      return api.post(`/workflow/tenders/${tender.id}/dispatch/`, {
        vendor: vendorId,
        method: 'OFFLINE',
      });
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['project-tender', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['project-vendors', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-stages'] }),
        queryClient.invalidateQueries({ queryKey: ['activities', projectId] }),
      ]);
    },
  });
  if (!enabled) return null;

  const tender = rowsFrom(tenderQuery.data)[0];
  const dispatches: Row[] = tender?.dispatches || [];
  const allSelectedVendorsDispatched = selections.length > 0
    && selections.every((vendor: Row) =>
      ['TENDER_SENT', 'BID_RECEIVED'].includes(vendor.participation_status),
    );

  function submitTecFormation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const memberIds = formData.getAll('member_ids').map(String);
    const chair = String(formData.get('chair') || '');
    if (!memberIds.length || !memberIds.includes(chair)) {
      setTecError('Select at least one TEC member and make sure the chair is included.');
      return;
    }
    setTecError('');
    formData.set('project', projectId);
    formData.set('committee_type', 'TEC');
    formData.set('chair', chair);
    createTec.mutate(formData);
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <b>Select vendors for the tender</b>
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
            Search verified vendor offerings against the products or services required for this project.
          </div>
        </div>
      </div>
      {selectionsQuery.isLoading ? <div className="empty">Loading vendor selection…</div> :
        selectionsQuery.isError ? <div role="alert" className="workflow-alert error">Could not load this project’s selected vendors.</div> :
          !tenderDraftApproved ? (
            <div className="workflow-panel-content">
              Vendor selection is available after the latest tender draft is approved by IA Wing.
            </div>
          ) : (
            <div className="workflow-panel-content">
              <form onSubmit={event => {
                event.preventDefault();
                search.mutate();
              }} style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                <input
                  aria-label="Required products or services"
                  value={requirement}
                  onChange={event => setRequirement(event.target.value)}
                  placeholder="Describe products or services, e.g. industrial printer"
                  minLength={2}
                  maxLength={500}
                  required
                  style={{ flex: '1 1 320px' }}
                />
                <button className="button primary" disabled={search.isPending || requirement.trim().length < 2}>
                  {search.isPending ? 'Searching vendors…' : 'Find matching vendors'}
                </button>
              </form>
              {search.isError && <div role="alert" className="workflow-alert error">Vendor search failed. Check the requirement and try again.</div>}
              {search.isSuccess && matches.length === 0 && (
                <div className="empty">No active, verified vendors matched those terms. Add offering details or categories to vendor records to improve results.</div>
              )}
              {matches.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <b>Recommended vendors</b>
                  <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
                    {matches.map((vendor: Row) => {
                      const alreadySelected = selections.some((item: Row) => item.vendor_id === vendor.id);
                      return (
                        <label key={vendor.id} className="card" style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                          <input
                            type="checkbox"
                            disabled={alreadySelected}
                            checked={alreadySelected || selectedIds.includes(vendor.id)}
                            onChange={event => setSelectedIds(current => event.target.checked
                              ? [...current, vendor.id]
                              : current.filter(id => id !== vendor.id))}
                          />
                          <span>
                            <b>{vendor.vendor_name}</b>
                            {alreadySelected ? ' · Already selected' : ` · ${vendor.similarity_score}% match`}
                            <br />
                            <span className="muted">{vendor.products_services || vendor.category_names?.join(', ') || 'No offering details provided'}</span>
                            {!!vendor.matched_terms?.length && (
                              <><br /><span className="muted">Matched: {vendor.matched_terms.join(', ')}</span></>
                            )}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                  <button
                    className="button primary"
                    disabled={!selectedIds.length || saveSelections.isPending}
                    onClick={() => saveSelections.mutate()}
                    style={{ marginTop: 12 }}
                  >
                    {saveSelections.isPending ? 'Saving selection…' : `Save selected vendors (${selectedIds.length})`}
                  </button>
                </div>
              )}
              {saveSelections.isError && <div role="alert" className="workflow-alert error">Could not save selected vendors. Confirm they are still active and verified.</div>}
              {removeSelection.isError && <div role="alert" className="workflow-alert error">Could not remove the vendor from this project.</div>}
              <div style={{ marginTop: 20 }}>
                <b>Selected vendors ({selections.length})</b>
                {selections.length ? (
                  <table>
                    <thead><tr><th>VENDOR</th><th>OFFERINGS</th><th>SELECTED</th><th>STATUS</th><th>ACTION</th></tr></thead>
                    <tbody>{selections.map((vendor: Row) => (
                      <tr key={vendor.vendor_id}>
                        <td>{vendor.vendor_name}</td>
                        <td>{vendor.products_services || vendor.category_names?.join(', ') || '—'}</td>
                        <td>{new Date(vendor.selected_at).toLocaleDateString()}</td>
                        <td>{vendor.participation_status.replaceAll('_', ' ')}</td>
                        <td>
                          {vendor.participation_status === 'SELECTED' && (
                            <button
                              className="icon-button"
                              disabled={removeSelection.isPending}
                              onClick={() => removeSelection.mutate(vendor.vendor_id)}
                            >
                              Remove
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}</tbody>
                  </table>
                ) : <div className="empty">No vendors have been selected for this project.</div>}
              </div>
              {!!selections.length && (
                <section style={{ marginTop: 24 }}>
                  <div className="panel-head">
                    <div>
                      <b>Offline tender dispatch</b>
                      <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                        Record when the approved tender is sent to each selected vendor offline. Bid receipt and bid uploads are a separate next step.
                      </div>
                    </div>
                  </div>
                  {tenderQuery.isLoading ? (
                    <div className="empty">Loading tender dispatches…</div>
                  ) : tenderQuery.isError ? (
                    <div role="alert" className="workflow-alert error">Could not load tender dispatch records.</div>
                  ) : (
                    <div style={{ display: 'grid', gap: 12 }}>
                      {selections.map((vendor: Row) => {
                        const vendorDispatches = dispatches.filter(
                          (item: Row) => item.vendor === vendor.vendor_id,
                        );
                        return (
                          <article className="card" key={vendor.vendor_id}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                              <div>
                                <b>{vendor.vendor_name}</b>
                                {vendorDispatches.map((item: Row) => (
                                  <div className="muted" key={item.id}>
                                    Offline dispatch recorded {new Date(item.dispatched_at).toLocaleString()}
                                  </div>
                                ))}
                                {!vendorDispatches.length && <div className="muted">Tender has not been marked as sent.</div>}
                              </div>
                              <button
                                type="button"
                                className="button primary"
                                disabled={recordDispatch.isPending || tenderQuery.isLoading}
                                onClick={() => recordDispatch.mutate(vendor.vendor_id)}
                              >
                                {recordDispatch.isPending
                                  ? 'Recording…'
                                  : vendorDispatches.length
                                    ? 'Record another offline dispatch'
                                      : 'Record tender sent offline'}
                              </button>
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  )}
                  {recordDispatch.isError && (
                    <div role="alert" className="workflow-alert error">
                      {messageFromError(recordDispatch.error)}
                    </div>
                  )}
                </section>
              )}
              <section className="panel project-tsc-panel" style={{ marginTop: 24 }}>
                <div className="panel-head">
                  <div>
                    <b>Technical Evaluation Committee (TEC) formation</b>
                    <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                      Admin proposes the TEC; it becomes active only after SS approval.
                    </div>
                  </div>
                </div>
                {tecError && <div role="alert" className="workflow-alert error">{tecError}</div>}
                {tec ? (
                  <div className="workflow-panel-content">
                    <div className="project-tsc-summary">
                      <div>
                        <b>{tec.committee_name}</b>
                        <div className="muted">
                          Chair: {tec.chair_name || 'Not set'}
                          {tec.chair_employee_id ? ` (${tec.chair_employee_id})` : ''}
                          {' · '}Members: {tec.members?.length || 0}
                        </div>
                        {tec.members?.length > 0 && (
                          <ul className="project-tsc-member-list" style={{ margin: '12px 0 0', paddingLeft: 18 }}>
                            {tec.members.map((member: Row) => (
                              <li key={member.id}>
                                {member.name}
                                {member.employee_id ? ` (${member.employee_id})` : ''}
                                {member.designation ? ` · ${member.designation}` : ''}
                                {member.user === tec.chair && ' · Chair'}
                                {member.roles?.some((role: string) => ['ADMIN', 'SUPER_ADMIN'].includes(role)) && ' · Admin'}
                              </li>
                            ))}
                          </ul>
                        )}
                        {tec.status === 'SUBMITTED' && (
                          <div className="muted">Awaiting SS approval. TEC members do not have project access until approval.</div>
                        )}
                        {tec.status === 'ACTIVE' && (
                          <div className="muted">SS approved this TEC; the committee is now formed.</div>
                        )}
                      </div>
                      <span className="status">{tec.status}</span>
                    </div>
                  </div>
                ) : !allSelectedVendorsDispatched ? (
                  <div className="workflow-panel-content">
                    Record tender dispatch to every selected vendor before proposing the TEC.
                  </div>
                ) : (
                  <form className="project-tsc-form" onSubmit={submitTecFormation}>
                    <label>
                      Committee name
                      <input name="committee_name" defaultValue="Technical Evaluation Committee" required />
                    </label>
                    <MemberSelector
                      employees={employees}
                      label="TEC members"
                      help="Select any members; the chair must also be selected."
                      ariaLabel="TEC member"
                    />
                    <label>
                      TEC chair
                      <select name="chair" required defaultValue="">
                        <option value="" disabled>Select chair</option>
                        {employees.map((person: Row) => (
                          <option key={person.id} value={person.id}>
                            {person.name}{person.employee_id ? ` (${person.employee_id})` : ''}
                            {person.roles?.some((role: string) => ['ADMIN', 'SUPER_ADMIN'].includes(role)) ? ' · Admin' : ''}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Supporting TEC formation PDF <span className="muted">(optional, max 10 MB)</span>
                      <input name="file" type="file" accept="application/pdf,.pdf" />
                    </label>
                    <div className="project-tsc-submit">
                      <button className="button primary" disabled={createTec.isPending || !employees.length}>
                        {createTec.isPending ? 'Sending for approval…' : 'Send TEC to SS for approval'}
                      </button>
                      {!employees.length && <span className="muted">No active, verified employees are available.</span>}
                    </div>
                    <small className="muted">
                      The chair must also be included in the committee members. SS approval activates the TEC and grants its members project access.
                    </small>
                  </form>
                )}
              </section>
            </div>
          )}
    </section>
  );
}

function ProjectTacWorkspace({
  projectId,
  userId,
  admin,
  committee,
  tacActive,
  isMember,
  tacFinancialComplete,
}: {
  projectId: string;
  userId: string;
  admin: boolean;
  committee: Row;
  tacActive: boolean;
  isMember: boolean;
  tacFinancialComplete: boolean;
}) {
  const queryClient = useQueryClient();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const qualificationQuery = useQuery({
    queryKey: ['qualified-vendors', projectId],
    queryFn: async () => (await api.get(`/projects/${projectId}/qualified-vendors/`)).data,
    enabled: admin,
  });
  const bidsQuery = useQuery({
    queryKey: ['project-bids', projectId, userId],
    queryFn: () => fetchAll(`/workflow/bids/?project=${projectId}`),
    enabled: admin || isMember,
  });
  const reportsQuery = useQuery({
    queryKey: ['tec-documents', projectId, userId],
    queryFn: () => fetchAll(`/workflow/tec-documents/?project=${projectId}`),
    enabled: admin || isMember,
  });
  const shortlistQuery = useQuery({
    queryKey: ['tac-shortlist', projectId, userId],
    queryFn: () => fetchAll(`/workflow/tac-shortlist/?project=${projectId}`),
    enabled: admin || isMember,
  });
  const tacDocumentsQuery = useQuery({
    queryKey: ['tac-documents', projectId, userId],
    queryFn: () => fetchAll(`/workflow/tac-documents/?project=${projectId}`),
    enabled: admin || isMember,
  });
  const finalSelectionQuery = useQuery({
    queryKey: ['tac-final-selection', projectId, userId],
    queryFn: async () => (await api.get(
      `/workflow/tac-shortlist/final-selection/?project=${projectId}`,
    )).data,
    enabled: admin || isMember,
  });
  const submitShortlist = useMutation({
    mutationFn: (data: FormData) => api.post('/workflow/tac-shortlist/select/', data),
    onSuccess: async () => {
      setSelectedIds([]);
      setError('');
      setNotice('The financial-bid shortlist was submitted to the TAC.');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['tac-shortlist', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['project-bids', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['tec-documents', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['notifications'] }),
        queryClient.invalidateQueries({ queryKey: ['activities', projectId] }),
      ]);
    },
    onError: (requestError: any) => {
      setNotice('');
      setError(messageFromError(requestError));
    },
  });
  const submitFinalReport = useMutation({
    mutationFn: (data: FormData) => api.post('/workflow/tac-documents/', data),
    onSuccess: async () => {
      setError('');
      setNotice('The final TAC report is available to Admin in this project.');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['tac-documents', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-stages', userId] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-dashboard', userId] }),
        queryClient.invalidateQueries({ queryKey: ['notifications'] }),
        queryClient.invalidateQueries({ queryKey: ['activities', projectId] }),
      ]);
    },
    onError: (requestError: any) => {
      setNotice('');
      setError(messageFromError(requestError));
    },
  });
  const submitFinalSelection = useMutation({
    mutationFn: (vendor: string) => api.post(
      '/workflow/tac-shortlist/final-selection/',
      { project: projectId, vendor },
    ),
    onSuccess: async () => {
      setError('');
      setNotice('The final vendor has been selected.');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['tac-final-selection', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-stages', userId] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-dashboard', userId] }),
        queryClient.invalidateQueries({ queryKey: ['notifications'] }),
        queryClient.invalidateQueries({ queryKey: ['activities', projectId] }),
      ]);
    },
    onError: (requestError: any) => {
      setNotice('');
      setError(messageFromError(requestError));
    },
  });

  const bids: Row[] = rowsFrom(bidsQuery.data);
  const shortlist: Row[] = rowsFrom(shortlistQuery.data);
  const finalReports = rowsFrom(reportsQuery.data).filter(
    (document: Row) => document.document_type === 'FINAL',
  );
  const finalTacReports: Row[] = rowsFrom(tacDocumentsQuery.data);
  const finalVendorSelection: Row | null = finalSelectionQuery.data;
  const isChair = committee.chair === userId;
  const candidates: Row[] = (qualificationQuery.data?.vendors || []).filter(
    (vendor: Row) => vendor.qualification_status === 'QUALIFIED'
      && bids.some((bid: Row) =>
        bid.vendor === vendor.vendor_id
        && bid.documents?.some((document: Row) => document.document_type === 'TECHNICAL'),
      ),
  );
  const requiredCount = Math.min(3, candidates.length);

  function submitFinancialBids(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const vendorIds = formData.getAll('vendor_ids').map(String);
    if (vendorIds.length !== requiredCount) {
      setError(`Select exactly ${requiredCount} vendor(s), based on the TEC report.`);
      return;
    }
    formData.set('project', projectId);
    setError('');
    submitShortlist.mutate(formData);
  }

  function submitTacReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    formData.set('committee', committee.id);
    setError('');
    submitFinalReport.mutate(formData, {
      onSuccess: () => form.reset(),
    });
  }

  return (
    <section
      className="panel"
      id="tac-financial-bids-panel"
      style={{ marginTop: 24, scrollMarginTop: 20 }}
    >
      <div className="panel-head">
        <div>
          <b>
            {admin
              ? 'Admin: select top vendors and upload financial bids'
              : `TAC review · ${committee.committee_name}`}
          </b>
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
            Review the TEC final report and Admin’s manually selected financial bids, then submit the TAC report.
          </div>
        </div>
      </div>
      {!tacActive ? (
        <div className="workflow-panel-content">
          TAC formation must be approved by SS before financial bids can be submitted or reviewed.
        </div>
      ) : reportsQuery.isLoading || shortlistQuery.isLoading || tacDocumentsQuery.isLoading
        || finalSelectionQuery.isLoading ? (
        <div className="empty">Loading TAC reports and bid documents…</div>
      ) : reportsQuery.isError || shortlistQuery.isError || tacDocumentsQuery.isError
        || finalSelectionQuery.isError
        ? (
        <div role="alert" className="workflow-alert error">
          Could not load TAC reports or financial-bid records.
        </div>
      ) : (
        <div className="workflow-panel-content">
          <section>
            <b>TEC final report</b>
            {finalReports.length ? (
              <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
                {finalReports.map((report: Row) => (
                  <article className="card" key={report.id}>
                    <b>{report.file_name} · Version {report.version}</b>
                    <div className="muted">
                      Submitted by {report.uploaded_by_name} · {new Date(report.uploaded_at).toLocaleString()}
                    </div>
                    <button
                      type="button"
                      className="icon-button"
                      onClick={() => downloadFile(report.file_url, report.file_name)}
                    >
                      Download TEC final report
                    </button>
                  </article>
                ))}
              </div>
            ) : (
              <div className="empty">The TEC final report is not available yet.</div>
            )}
          </section>

          <section style={{ marginTop: 20 }}>
            <b>Top vendors · financial bids</b>
            {shortlist.length ? (
              <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
                {shortlist.map((item: Row) => (
                  <article className="card" key={item.id}>
                    <b>{item.vendor_name}</b>
                    <div className="muted">
                      Selected by {item.selected_by_name} · {new Date(item.selected_at).toLocaleString()}
                    </div>
                    <button
                      type="button"
                      className="icon-button"
                      onClick={() => downloadFile(
                        item.financial_document.file_url,
                        `${item.vendor_name}-financial-bid.pdf`,
                      )}
                    >
                      Download financial bid · Version {item.financial_document.version}
                    </button>
                  </article>
                ))}
              </div>
            ) : admin ? (
              qualificationQuery.isLoading || bidsQuery.isLoading ? (
                <div className="empty">Loading technically qualified vendors…</div>
              ) : qualificationQuery.isError || bidsQuery.isError ? (
                <div role="alert" className="workflow-alert error">
                  Could not load qualified vendors and technical bids.
                </div>
              ) : !qualificationQuery.data?.qualification_complete ? (
                <div className="empty">Complete vendor qualification before selecting the financial-bid shortlist.</div>
              ) : !finalReports.length ? (
                <div className="empty">The TAC shortlist unlocks after the TEC final report is submitted.</div>
              ) : !candidates.length ? (
                <div className="empty">No technically evaluated, qualified vendors are available.</div>
              ) : (
                <form onSubmit={submitFinancialBids} style={{ display: 'grid', gap: 10, marginTop: 8 }}>
                  <div className="muted">
                    Select exactly {requiredCount} qualified vendor{requiredCount === 1 ? '' : 's'} based on the TEC report, then upload each vendor’s financial bid PDF. The selection becomes locked after submission.
                  </div>
                  {candidates.map((vendor: Row) => {
                    const checked = selectedIds.includes(vendor.vendor_id);
                    return (
                      <article className="card" key={vendor.vendor_id} style={{ display: 'grid', gap: 8 }}>
                        <label style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                          <input
                            type="checkbox"
                            name="vendor_ids"
                            value={vendor.vendor_id}
                            checked={checked}
                            onChange={event => setSelectedIds(current => event.target.checked
                              ? [...current, vendor.vendor_id]
                              : current.filter(id => id !== vendor.vendor_id))}
                            disabled={!checked && selectedIds.length >= requiredCount}
                          />
                          <b>{vendor.vendor_name}</b>
                        </label>
                        <label className="muted">
                          Financial bid PDF
                          <input
                            name={`financial_file_${vendor.vendor_id}`}
                            type="file"
                            accept="application/pdf,.pdf"
                            required={checked}
                            disabled={!checked}
                          />
                        </label>
                      </article>
                    );
                  })}
                  <button
                    className="button primary"
                    disabled={submitShortlist.isPending || selectedIds.length !== requiredCount}
                  >
                    {submitShortlist.isPending ? 'Submitting financial bids…' : 'Submit shortlist and financial bids to TAC'}
                  </button>
                  {error && <div role="alert" className="workflow-alert error">{error}</div>}
                  {notice && <div role="status" className="workflow-alert success">{notice}</div>}
                </form>
              )
            ) : (
              <div className="empty">Admin has not yet submitted the top-vendor financial bids.</div>
            )}
            {error && shortlist.length > 0 && (
              <div role="alert" className="workflow-alert error">{error}</div>
            )}
            {notice && shortlist.length > 0 && (
              <div role="status" className="workflow-alert success">{notice}</div>
            )}
          </section>

          <section style={{ marginTop: 20 }}>
            <div id="tac-final-report-panel" style={{ scrollMarginTop: 20 }}>
              <b>Final TAC report</b>
            </div>
            {finalTacReports.length ? (
              <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
                {finalTacReports.map((report: Row) => (
                  <article className="card" key={report.id}>
                    <b>{report.file_name} · Version {report.version}</b>
                    <div className="muted">
                      Submitted by {report.uploaded_by_name} · {new Date(report.uploaded_at).toLocaleString()}
                    </div>
                    <button
                      type="button"
                      className="icon-button"
                      onClick={() => downloadFile(report.file_url, report.file_name)}
                    >
                      Download final TAC report
                    </button>
                  </article>
                ))}
              </div>
            ) : (
              <div className="empty">
                {tacFinancialComplete
                  ? 'The TAC chair has not submitted the final report yet.'
                  : 'The final report upload unlocks after Admin submits the financial bids.'}
              </div>
            )}
            {tacActive && isChair && tacFinancialComplete && (
              <form onSubmit={submitTacReport} style={{ display: 'grid', gap: 10, marginTop: 12 }}>
                <label>
                  {finalTacReports.length ? 'Upload revised final report PDF' : 'Final TAC report PDF'}
                  <input name="file" type="file" accept="application/pdf,.pdf" required />
                </label>
                <button
                  className="button primary"
                  disabled={submitFinalReport.isPending}
                >
                  {submitFinalReport.isPending
                    ? 'Uploading final report…'
                    : finalTacReports.length
                      ? 'Upload revised final TAC report'
                      : 'Upload final TAC report'}
                </button>
              </form>
            )}
          </section>
          <section
            id="tac-final-vendor-panel"
            style={{ marginTop: 20, scrollMarginTop: 20 }}
          >
            <b>Final vendor selection · Admin</b>
            {finalVendorSelection ? (
              <article className="card" style={{ marginTop: 8 }}>
                <b>{finalVendorSelection.vendor_name}</b>
                <div className="muted">
                  Selected by {finalVendorSelection.selected_by_name} ·{' '}
                  {new Date(finalVendorSelection.decided_at).toLocaleString()}
                </div>
              </article>
            ) : !finalTacReports.length ? (
              <div className="empty">
                Final vendor selection unlocks after the TAC chair submits the final report.
              </div>
            ) : shortlist.length === 0 ? (
              <div className="empty">There are no shortlisted vendors to select.</div>
            ) : admin ? (
              <form
                onSubmit={event => {
                  event.preventDefault();
                  const vendor = String(new FormData(event.currentTarget).get('vendor') || '');
                  if (vendor) submitFinalSelection.mutate(vendor);
                }}
                style={{ display: 'grid', gap: 10, marginTop: 8 }}
              >
                <label>
                  Choose the final vendor from the TAC shortlist
                  <select name="vendor" required defaultValue="">
                    <option value="" disabled>Select a vendor</option>
                    {shortlist.map((item: Row) => (
                      <option key={item.vendor} value={item.vendor}>{item.vendor_name}</option>
                    ))}
                  </select>
                </label>
                <button className="button primary" disabled={submitFinalSelection.isPending}>
                  {submitFinalSelection.isPending ? 'Saving final vendor…' : 'Select final vendor'}
                </button>
              </form>
            ) : (
              <div className="empty">Admin has not selected a final vendor yet.</div>
            )}
          </section>
          {error && <div role="alert" className="workflow-alert error">{error}</div>}
          {notice && <div role="status" className="workflow-alert success">{notice}</div>}
        </div>
      )}
    </section>
  );
}

function ProjectTacFormation({
  projectId,
  userId,
  qualificationComplete,
  committee,
  employees,
}: {
  projectId: string;
  userId: string;
  qualificationComplete: boolean;
  committee?: Row;
  employees: Row[];
}) {
  const queryClient = useQueryClient();
  const [error, setError] = useState('');
  const createTac = useMutation({
    mutationFn: (data: FormData) => api.post('/workflow/committees/', data),
    onSuccess: async () => {
      setError('');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workflow-committees', userId] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-submissions', userId] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-dashboard', userId] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-stages', userId] }),
        queryClient.invalidateQueries({ queryKey: ['notifications'] }),
        queryClient.invalidateQueries({ queryKey: ['activities', projectId] }),
      ]);
    },
    onError: (requestError: any) => setError(messageFromError(requestError)),
  });

  function submitTacFormation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const memberIds = formData.getAll('member_ids').map(String);
    const iaWingMembers = employees.filter(
      (person: Row) => memberIds.includes(person.id) && person.roles?.includes('IA_WING'),
    );
    const chair = String(formData.get('chair') || '');
    if (memberIds.length < 2) {
      setError('Select the IA Wing representative and at least one other TAC member.');
      return;
    }
    if (iaWingMembers.length !== 1) {
      setError('Select exactly one active, verified IA Wing user as a TAC member.');
      return;
    }
    if (!memberIds.includes(chair)) {
      setError('Select a TAC chair who is included in the committee.');
      return;
    }
    setError('');
    formData.set('project', projectId);
    formData.set('committee_type', 'TAC');
    formData.set('chair', chair);
    createTac.mutate(formData);
  }

  return (
    <section className="panel project-tsc-panel">
      <div className="panel-head">
        <div>
          <b>Tender Acceptance Committee (TAC) formation</b>
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
            Admin proposes the TAC after vendor qualification. SS approval activates the committee.
          </div>
        </div>
      </div>
      {error && <div role="alert" className="workflow-alert error">{error}</div>}
      {!qualificationComplete ? (
        <div className="workflow-panel-content">
          TAC formation is locked until Admin completes vendor qualification.
        </div>
      ) : committee ? (
        <div className="workflow-panel-content">
          <div className="project-tsc-summary">
            <div>
              <b>{committee.committee_name}</b>
              <div className="muted">
                Chair: {committee.chair_name || 'Not set'}
                {committee.chair_employee_id ? ` (${committee.chair_employee_id})` : ''}
                {' · '}Members: {committee.members?.length || 0}
              </div>
              {committee.members?.length > 0 && (
                <ul className="project-tsc-member-list" style={{ margin: '12px 0 0', paddingLeft: 18 }}>
                  {committee.members.map((member: Row) => (
                    <li key={member.id}>
                      {member.name}
                      {member.employee_id ? ` (${member.employee_id})` : ''}
                      {member.designation ? ` · ${member.designation}` : ''}
                      {member.user === committee.chair && ' · Chair'}
                      {member.roles?.some((role: string) => ['ADMIN', 'SUPER_ADMIN'].includes(role)) && ' · Admin'}
                      {member.roles?.includes('IA_WING') && ' · IA Wing — TAC member'}
                    </li>
                  ))}
                </ul>
              )}
              {committee.status === 'SUBMITTED' && (
                <div className="muted">Awaiting SS approval. TAC members will get project access after approval.</div>
              )}
              {committee.status === 'ACTIVE' && (
                <div className="muted">SS approved this TAC; the committee is now formed.</div>
              )}
            </div>
            <span className="status">{committee.status}</span>
          </div>
        </div>
      ) : (
        <form className="project-tsc-form" onSubmit={submitTacFormation}>
          <label>
            Committee name
            <input name="committee_name" defaultValue="Tender Acceptance Committee" required />
          </label>
          <MemberSelector
            employees={employees}
            label="TAC members"
            help="Select any members, including exactly one IA Wing representative. The chair must also be selected."
            ariaLabel="TAC member"
          />
          <label>
            TAC chair
            <select name="chair" required defaultValue="">
              <option value="" disabled>Select chair</option>
              {employees.map((person: Row) => (
                <option key={person.id} value={person.id}>
                  {person.name}{person.employee_id ? ` (${person.employee_id})` : ` (${person.email})`}
                  {person.roles?.includes('IA_WING') ? ' · IA Wing' : ''}
                  {person.roles?.some((role: string) => ['ADMIN', 'SUPER_ADMIN'].includes(role)) ? ' · Admin' : ''}
                </option>
              ))}
            </select>
          </label>
          <label>
            Supporting TAC formation PDF <span className="muted">(optional, max 10 MB)</span>
            <input name="file" type="file" accept="application/pdf,.pdf" />
          </label>
          <div className="project-tsc-submit">
            <button
              className="button primary"
              disabled={createTac.isPending || employees.length < 2 || !employees.some((person: Row) => person.roles?.includes('IA_WING'))}
            >
              {createTac.isPending ? 'Sending for approval…' : 'Send TAC to SS for approval'}
            </button>
            {(!employees.some((person: Row) => person.roles?.includes('IA_WING')) || employees.length < 2) && (
              <span className="muted">An active, verified IA Wing user and at least one other active, verified user are required.</span>
            )}
          </div>
          <small className="muted">
            Exactly one IA Wing user must be selected as a TAC member. Admin is not added automatically. The chair must be included in the committee; membership becomes active only after SS approval.
          </small>
        </form>
      )}
    </section>
  );
}

function CommitteeQueryResponseForm({
  committee,
  committeeType,
  approverRole,
  employees,
  submission,
  busy,
  onCancel,
  onSubmit,
  setError,
}: {
  committee: Row;
  committeeType: 'TSC' | 'TEC' | 'TAC';
  approverRole: 'SS';
  employees: Row[];
  submission: Row;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (values: FormData) => Promise<void>;
  setError: (message: string) => void;
}) {
  return (
    <form className="project-tsc-form" onSubmit={async event => {
      event.preventDefault();
      const values = new FormData(event.currentTarget);
      const memberIds = [...new Set(values.getAll('member_ids').map(String))];
      const iaWingMembers = employees.filter(
        (person: Row) => memberIds.includes(person.id) && person.roles?.includes('IA_WING'),
      );
      const chair = String(values.get('chair') || '');
      const comment = String(values.get('comment') || '').trim();
      if (memberIds.length < (committeeType === 'TAC' ? 2 : 1) || !memberIds.includes(chair)) {
        setError('Select at least one member and make sure the chair is included in the committee.');
        return;
      }
      if (committeeType === 'TAC' && iaWingMembers.length !== 1) {
        setError('Select exactly one active, verified IA Wing user as a TAC member.');
        return;
      }
      if (!comment) {
        setError('Enter a response to the SS query.');
        return;
      }
      values.delete('member_ids');
      memberIds.forEach(memberId => values.append('member_ids', memberId));
      values.set('comment', comment);
      values.set('chair', chair);
      await onSubmit(values);
    }}>
      <div>
        <b>Edit {committeeType} and respond to {approverRole}</b>
        <div className="muted" style={{ marginTop: 4 }}>
          Add a PDF if it supports your response. It is optional and limited to 10 MB.
        </div>
      </div>
      {submission.file_url && (
        <div className="muted">
          A supporting PDF is already attached. Uploading another file will replace it.
          {' '}
          <button type="button" className="icon-button" onClick={() =>
            downloadFile(submission.file_url, `${submission.title}.pdf`)
          }>Download current PDF</button>
        </div>
      )}
      <label>
        Committee name
        <input name="committee_name" defaultValue={committee.committee_name} required />
      </label>
      <MemberSelector
        employees={employees}
        label={`${committeeType} members`}
        help={committeeType === 'TAC'
          ? 'Select any members, including exactly one IA Wing representative. The chair must also be selected.'
          : 'Select any members; the chair must also be selected.'}
        ariaLabel={`${committeeType} member`}
        defaultSelectedIds={(committee.members || []).map((member: Row) => member.user)}
      />
      <label>
        {committeeType} chair
        <select name="chair" required defaultValue={committee.chair}>
          <option value="" disabled>Select chair</option>
          {employees.map((person: Row) => (
            <option key={person.id} value={person.id}>{person.name} ({person.email})</option>
          ))}
        </select>
      </label>
      <label>
        Response to {approverRole}
        <textarea name="comment" required placeholder={`Explain the changes made to the ${committeeType}.`} />
      </label>
      <label>
        Supporting PDF (optional, max 10 MB)
        <input name="file" type="file" accept="application/pdf,.pdf" />
      </label>
      <div style={{ display: 'flex', gap: 8 }}>
        <button className="button primary" disabled={busy}>
          {busy ? 'Resubmitting…' : 'Save changes and resend for approval'}
        </button>
        <button type="button" className="icon-button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
