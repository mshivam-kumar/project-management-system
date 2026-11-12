from django.db import migrations
from django.utils import timezone


def configure_policy(apps, database, submission_type, roles, name, creator):
    ApprovalPolicy = apps.get_model("workflow", "ApprovalPolicy")
    ApprovalPolicyLevel = apps.get_model("workflow", "ApprovalPolicyLevel")

    policy = ApprovalPolicy.objects.using(database).filter(
        submission_type=submission_type,
        is_active=True,
    ).first()
    if not policy:
        if not creator:
            return None
        policy = ApprovalPolicy.objects.using(database).create(
            name=name,
            submission_type=submission_type,
            is_active=True,
            created_by_id=creator.pk,
        )
    ApprovalPolicyLevel.objects.using(database).filter(policy_id=policy.pk).delete()
    ApprovalPolicyLevel.objects.using(database).bulk_create([
        ApprovalPolicyLevel(
            policy_id=policy.pk,
            sequence=sequence,
            approver_role=role,
        )
        for sequence, role in enumerate(roles, start=1)
    ])
    ApprovalPolicy.objects.using(database).filter(pk=policy.pk).update(name=name)
    return policy


def add_hq_report_approvals(apps, schema_editor):
    database = schema_editor.connection.alias
    Role = apps.get_model("accounts", "Role")
    User = apps.get_model("accounts", "User")
    Committee = apps.get_model("committees", "Committee")
    ProjectStage = apps.get_model("workflow", "ProjectStage")
    TECWorkDocument = apps.get_model("workflow", "TECWorkDocument")
    StageSubmission = apps.get_model("workflow", "StageSubmission")
    ApprovalPolicy = apps.get_model("workflow", "ApprovalPolicy")
    ApprovalRequest = apps.get_model("workflow", "ApprovalRequest")
    ApprovalStep = apps.get_model("workflow", "ApprovalStep")
    ApprovalEvent = apps.get_model("workflow", "ApprovalEvent")

    Role.objects.using(database).get_or_create(
        name="HQ",
        defaults={"description": "Headquarters approval authority"},
    )
    creator = User.objects.using(database).order_by("created_at").first()
    tsc_policy = configure_policy(
        apps,
        database,
        "TSC_REPORT",
        ["AS", "HQ"],
        "TSC Report - AS and HQ Approval",
        creator,
    )
    tec_policy = configure_policy(
        apps,
        database,
        "TEC_REPORT",
        ["HQ"],
        "TEC Report - HQ Approval",
        creator,
    )

    if not tec_policy:
        tec_policy = ApprovalPolicy.objects.using(database).filter(
            submission_type="TEC_REPORT",
            is_active=True,
        ).first()
    if not tec_policy:
        return

    committees = Committee.objects.using(database).filter(
        committee_type="TEC",
        status="ACTIVE",
    ).order_by("formed_at")
    for committee in committees.iterator():
        report_stage = ProjectStage.objects.using(database).filter(
            project_id=committee.project_id,
            stage_type="TEC_REPORT",
        ).first()
        if not report_stage:
            continue
        if StageSubmission.objects.using(database).filter(
            committee_id=committee.pk,
            submission_type="TEC_REPORT",
        ).exists():
            continue
        report = TECWorkDocument.objects.using(database).filter(
            committee_id=committee.pk,
            document_type="FINAL",
        ).order_by("-version", "-uploaded_at").first()
        if not report:
            continue

        submission = StageSubmission.objects.using(database).create(
            stage_id=report_stage.pk,
            committee_id=committee.pk,
            submission_type="TEC_REPORT",
            revision=1,
            submitted_by_id=report.uploaded_by_id,
            title="TEC Final Report",
            file=report.file.name,
            status="IN_REVIEW",
        )
        approval_request = ApprovalRequest.objects.using(database).create(
            submission_id=submission.pk,
            policy_id=tec_policy.pk,
            policy_name=tec_policy.name,
            status="IN_PROGRESS",
        )
        step = ApprovalStep.objects.using(database).create(
            request_id=approval_request.pk,
            sequence=1,
            approver_role="HQ",
            status="PENDING",
        )
        ApprovalEvent.objects.using(database).create(
            request_id=approval_request.pk,
            step_id=step.pk,
            actor_id=report.uploaded_by_id,
            action="SUBMITTED",
            comment="Existing TEC final report queued for HQ approval.",
        )
        report_stage.status = "WAITING_APPROVAL"
        report_stage.completed_at = None
        report_stage.actual_start = report_stage.actual_start or timezone.now()
        report_stage.save(update_fields=[
            "status", "completed_at", "actual_start",
        ])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_user_employee_id"),
        ("workflow", "0023_restore_admin_final_vendor_selection"),
    ]

    operations = [
        migrations.RunPython(
            add_hq_report_approvals,
            migrations.RunPython.noop,
        ),
    ]
