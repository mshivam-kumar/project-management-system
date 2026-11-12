import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api } from '../services/api';
import type { User } from '../types';

type Row = Record<string, any>;

function messageFromError(error: any) {
  const data = error.response?.data;
  if (typeof data === 'string') return data;
  if (data?.detail) return data.detail;
  if (data) return Object.entries(data).map(([key, value]) => `${key}: ${String(value)}`).join(' ');
  return 'The request failed. Please try again.';
}

function dateLabel(value: string | null) {
  return value ? new Date(`${value}T00:00:00`).toLocaleDateString() : 'Not scheduled';
}

function submissionTypeLabel(type?: string) {
  const labels: Record<string, string> = {
    TSC_FORMATION: 'TSC formation · SS approval',
    TSC_REPORT: 'TSC report · AS → HQ approval',
    TSC_REPORT_LEVEL3: 'TSC report · DGS approval',
    TEC_REPORT: 'TEC final report · HQ approval',
    TENDER_DRAFT: 'Tender draft · IA Wing approval',
  };
  return type ? labels[type] || type.replace(/_/g, ' ') : '';
}

function submissionTitleLabel(item: Row) {
  if (item.submission_type === 'TSC_REPORT') return 'TSC Report — AS/HQ Review';
  if (item.submission_type === 'TSC_REPORT_LEVEL3') return 'TSC Report — DGS Review';
  if (item.submission_type === 'TEC_REPORT') return 'TEC Final Report — HQ Review';
  return item.title || 'Submission';
}

export default function ApprovalInbox({ user, projectId }: { user: User; projectId?: string }) {
  const queryClient = useQueryClient();
  const canReview = user.roles.some(role => ['SS', 'AS', 'HQ', 'DGS', 'IA_WING'].includes(role));
  const canReviewFormation = user.roles.includes('SS');
  const canReviewTscReport = user.roles.includes('AS') || user.roles.includes('HQ');
  const canReviewTecReport = user.roles.includes('HQ');
  const canReviewDgsTscReport = user.roles.includes('DGS');
  const canReviewTenderDraft = user.roles.includes('IA_WING');
  const isAsOnly = user.roles.includes('AS') && !user.roles.includes('HQ') && !canReviewFormation;
  const isHqOnly = user.roles.includes('HQ') && !canReviewFormation
    && !user.roles.includes('AS') && !canReviewDgsTscReport && !canReviewTenderDraft;
  const isDgsOnly = canReviewDgsTscReport && !canReviewFormation && !canReviewTscReport;
  const isIaWingOnly = canReviewTenderDraft
    && !canReviewFormation
    && !canReviewTscReport
    && !canReviewDgsTscReport;
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [pdfPreview, setPdfPreview] = useState<{ submissionId: string; url: string } | null>(null);
  useEffect(() => () => {
    if (pdfPreview) URL.revokeObjectURL(pdfPreview.url);
  }, [pdfPreview]);
  const dashboard = useQuery({
    queryKey: ['workflow-dashboard', user.id],
    queryFn: async () => (await api.get('/workflow/dashboard/')).data,
    enabled: canReview,
  });
  const action = useMutation({
    mutationFn: ({ url, data }: { url: string; data: { comment: string } }) =>
      api.post(url, data),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workflow-dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['workflow-submissions'] }),
        queryClient.invalidateQueries({ queryKey: ['notifications'] }),
        queryClient.invalidateQueries({ queryKey: ['projects'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] }),
      ]);
      setError('');
      setNotice('Approval action recorded.');
    },
    onError: (requestError: any) => {
      setNotice('');
      setError(messageFromError(requestError));
    },
  });

  async function review(item: Row, decision: 'approve' | 'query' | 'reject') {
    const comment = decision === 'approve' ? '' : window.prompt(
      decision === 'query' ? 'Enter the query for the submitter:' : 'Enter the rejection reason:',
    );
    if (decision !== 'approve' && !comment?.trim()) return;
    await action.mutateAsync({
      url: `/workflow/submissions/${item.submission_id}/${decision === 'query' ? 'query' : decision}/`,
      data: { comment: comment || '' },
    });
  }

  if (!canReview) return null;

  const approvals: Row[] = (dashboard.data?.pending_approvals || []).filter(
    (item: Row) =>
      (!projectId || item.project_id === projectId) &&
      (!['TSC_FORMATION', 'TEC_FORMATION', 'TAC_FORMATION'].includes(item.submission_type) || canReviewFormation) &&
      (item.submission_type !== 'TSC_REPORT' || canReviewTscReport) &&
      (item.submission_type !== 'TSC_REPORT_LEVEL3' || canReviewDgsTscReport) &&
      (item.submission_type !== 'TEC_REPORT' || canReviewTecReport) &&
      (item.submission_type !== 'TENDER_DRAFT' || canReviewTenderDraft),
  );

  async function viewPdf(item: Row) {
    try {
      const response = await api.get(item.file_url, { responseType: 'blob' });
      if (pdfPreview) URL.revokeObjectURL(pdfPreview.url);
      setPdfPreview({
        submissionId: item.submission_id,
        url: URL.createObjectURL(response.data),
      });
      setError('');
    } catch (requestError: any) {
      setError(messageFromError(requestError));
    }
  }

  async function downloadPdf(item: Row) {
    try {
      const response = await api.get(item.file_url, { responseType: 'blob' });
      const objectUrl = URL.createObjectURL(response.data);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = `${item.title || 'TSC-formation'}.pdf`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      setError('');
    } catch (requestError: any) {
      setError(messageFromError(requestError));
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <b>
            {isAsOnly || isDgsOnly || isHqOnly
              ? isHqOnly ? 'HQ report approvals' : 'TSC report approvals'
              : isIaWingOnly
                ? 'Tender draft approvals'
                : 'Approvals and responses'}
          </b>
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
            {isAsOnly || isDgsOnly || isHqOnly
              ? `Review reports submitted by committee chairs for ${isDgsOnly ? 'DGS' : isHqOnly ? 'HQ' : 'AS'}.`
              : isIaWingOnly
              ? 'Review tender drafts submitted by the admin for IA Wing.'
              : 'Review submission details before making a decision.'}
          </div>
        </div>
        {!projectId && <Link className="button project-details-button" to="/projects">Open projects</Link>}
      </div>
      {error && <div role="alert" className="workflow-alert error">{error}</div>}
      {notice && <div role="status" className="workflow-alert success">{notice}</div>}
      {dashboard.isLoading ? <div className="empty">Loading approvals…</div> :
        dashboard.isError ? <div role="alert" className="empty">Could not load approvals. Please retry.</div> : (
          approvals.length ? (
            <div style={{ display: 'grid', gap: 14, padding: 16 }}>
              {approvals.map((item: Row) => {
                const awaitingResponse = item.step_status === 'QUERY';
                const isTscReport = [
                  'TSC_REPORT',
                  'TSC_REPORT_LEVEL3',
                ].includes(item.submission_type);
                const isTecReport = item.submission_type === 'TEC_REPORT';
                const isReport = isTscReport || isTecReport;
                const reportRole = item.approver_role
                  || (isTecReport ? 'HQ' : item.submission_type === 'TSC_REPORT_LEVEL3' ? 'DGS' : 'AS');
                const isTenderDraft = item.submission_type === 'TENDER_DRAFT';
                return (
                  <article key={item.id} className="panel" style={{ margin: 0, padding: 16 }}>
                    <div className="project-tsc-summary">
                      <div>
                        <b>{item.project_code} · {item.project?.title}</b>
                        <div className="muted">
                          {isReport
                            ? `${isTecReport ? 'TEC' : 'TSC'} report submitted for ${reportRole} approval`
                            : isTenderDraft
                              ? 'Tender draft submitted for IA Wing approval'
                              : `${item.title} · ${submissionTypeLabel(item.submission_type)}`}
                        </div>
                      </div>
                      <span className="status">
                        {awaitingResponse
                          ? 'Awaiting response'
                          : isReport
                            ? `${reportRole} report review`
                            : isTenderDraft
                              ? 'IA Wing tender review'
                              : 'Approval required'}
                      </span>
                    </div>

                    <details open style={{ marginTop: 12 }}>
                      <summary>
                        {isReport
                          ? `Review the ${isTecReport ? 'TEC' : 'TSC'} report for ${reportRole}`
                          : isTenderDraft
                            ? 'Review the tender draft'
                            : 'Review submission details'}
                      </summary>
                      <div style={{ marginTop: 8 }}>
                        {isReport && (
                          <div className="project-tsc-summary" style={{ marginBottom: 12 }}>
                            <div>
                              <b>Report: {submissionTitleLabel(item)}</b>
                              <div className="muted">
                                Submitted by {item.submitted_by || item.committee?.chair?.name || `${isTecReport ? 'TEC' : 'TSC'} chair`}
                                {item.submitted_at && ` · ${new Date(item.submitted_at).toLocaleString()}`}
                              </div>
                            </div>
                          </div>
                        )}
                        {isReport && item.comments && <div><b>Report notes:</b> {item.comments}</div>}
                        <div><b>Department:</b> {item.project?.department || '—'}</div>
                        <div><b>Estimated amount:</b> {Number(item.project?.estimated_amount || 0).toLocaleString('en-IN', {
                          style: 'currency',
                          currency: 'INR',
                          maximumFractionDigits: 0,
                        })}</div>
                        <div><b>Project status:</b> {item.project?.status?.replaceAll('_', ' ') || '—'}</div>
                        <div><b>Created by:</b> {item.project?.created_by || '—'}</div>
                        {isTenderDraft && (
                          <div style={{ marginTop: 10 }}>
                            <div><b>Expected tender dispatch to vendors:</b> {dateLabel(item.expected_vendor_dispatch_date)}</div>
                            <div><b>Expected bid receipt deadline:</b> {dateLabel(item.expected_bid_receipt_date)}</div>
                            <div><b>Expected product arrival:</b> {dateLabel(item.expected_product_arrival_date)}</div>
                          </div>
                        )}
                        <div><b>Created:</b> {item.project?.created_at ? new Date(item.project.created_at).toLocaleString() : '—'}</div>
                        <div><b>Project description:</b> {item.project?.description || 'No description provided.'}</div>
                        <div><b>Approval due:</b> {dateLabel(item.due_date)}</div>
                        {item.committee && (
                          <div style={{ marginTop: 10 }}>
                            <b>{item.committee.type}: {item.committee.name}</b>
                            <div>
                              <b>{item.committee.type} chair:</b> {item.committee.chair?.name || 'Not assigned'}
                              {item.committee.chair?.email && ` (${item.committee.chair.email})`}
                            </div>
                            {!isTscReport && (
                              <>
                                <div><b>Selected members ({item.committee.members.length}):</b></div>
                                {item.committee.members.length ? (
                                  <ul style={{ marginTop: 4, paddingLeft: 20 }}>
                                    {item.committee.members.map((member: Row) => (
                                      <li key={member.email}>
                                        {member.name} ({member.email})
                                        {member.designation && ` · ${member.designation}`}
                                      </li>
                                    ))}
                                  </ul>
                                ) : <div className="muted">No members selected.</div>}
                              </>
                            )}
                          </div>
                        )}
                        {!isReport && item.comments && <div><b>Submission comments:</b> {item.comments}</div>}
                        {!isReport && item.file_url && (
                          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                            <button className="icon-button" disabled={dashboard.isFetching} onClick={() => viewPdf(item)}>
                              View attached PDF
                            </button>
                            <button className="icon-button" disabled={dashboard.isFetching} onClick={() => downloadPdf(item)}>
                              Download attached PDF
                            </button>
                          </div>
                        )}
                        {pdfPreview && pdfPreview.submissionId === item.submission_id && (
                          <iframe
                            title={`${item.title} PDF`}
                            src={pdfPreview.url}
                            style={{ width: '100%', height: 560, border: '1px solid #e7ecf2', borderRadius: 8, marginTop: 12 }}
                          />
                        )}
                      </div>
                    </details>

                    {awaitingResponse ? (
                      <div className="muted" style={{ marginTop: 12 }}>
                        A query has been sent to the submitter. Approval or rejection will be available after they respond.
                      </div>
                    ) : (
                      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                        <button className="button primary" disabled={action.isPending} onClick={() => review(item, 'approve')}>
                          {isReport
                            ? `Approve ${isTecReport ? 'TEC' : 'TSC'} report — ${reportRole}`
                            : isTenderDraft
                              ? 'Approve tender draft'
                              : 'Approve'}
                        </button>
                        <button className="icon-button" disabled={action.isPending} onClick={() => review(item, 'query')}>
                          {isReport
                            ? `Query on ${isTecReport ? 'TEC' : 'TSC'} report — ${reportRole}`
                            : isTenderDraft
                              ? 'Query on tender draft'
                              : 'Query'}
                        </button>
                        <button className="icon-button" disabled={action.isPending} onClick={() => review(item, 'reject')}>
                          {isReport
                            ? `Reject ${isTecReport ? 'TEC' : 'TSC'} report — ${reportRole}`
                            : isTenderDraft
                              ? 'Reject tender draft'
                              : 'Reject'}
                        </button>
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          ) : <div className="empty">No approvals or responses require your attention.</div>
        )}
    </section>
  );
}
